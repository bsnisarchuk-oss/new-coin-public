from __future__ import annotations

import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.callback_data import (
    MuteExchangeCB,
    MuteMenuBackCB,
    MuteMenuCB,
    MuteTickerCB,
    QuickAlertCB,
    SubMuteExchangeCB,
    SubMuteTickerCB,
    TrackCB,
    WatchCB,
)
from app.bot.keyboards.event_actions import build_event_actions, build_mute_submenu
from app.bot.lang import preferred_lang
from app.config import Settings
from app.db.models import Event, MuteType
from app.db.repo import analytics as analytics_repo
from app.db.repo import events as events_repo
from app.db.repo import mutes as mutes_repo
from app.db.repo import price_alerts as alerts_repo
from app.db.repo import users as users_repo
from app.db.repo import watchlist as watchlist_repo
from app.services.tracker import TrackerService

router = Router()

_ALERT_PRICE_RE = re.compile(r"^([><])\s*([\d.]+)")


class QuickAlertState(StatesGroup):
    waiting_price = State()


def _text(key: str, lang: str, **kwargs: str | int | Decimal) -> str:
    ru = {
        "ticker_unknown": "Ticker не распознан",
        "watch_done": "{ticker} добавлен в избранное",
        "invalid_event_id": "Некорректный event id",
        "event_missing": "Событие не найдено",
        "track_exists": "Трекинг уже включён",
        "track_done": "Трекинг включён: отчёты через 15m, 1h, 4h и 24h",
        "exchange_unknown": "Exchange не распознан",
        "mute_ticker_done": "{ticker} замолчан",
        "mute_exchange_done": "{exchange} замолчан",
        "mute_ticker_alert": "🔕 {ticker} замолчан — листинги этой монеты больше не придут",
        "mute_exchange_alert": "🔕 {exchange} замолчан — листинги этой биржи больше не придут",
        "quick_alert.price_hint": "\nТекущая цена: <b>${price}</b>",
        "quick_alert.prompt": (
            "🔔 Алерт для <b>{ticker}</b> на {exchange}{price_hint}\n\n"
            "Введи порог срабатывания:\n"
            "<code>&gt; 50000</code> — уведомить когда цена вырастет выше\n"
            "<code>&lt; 1000</code> — уведомить когда цена упадёт ниже\n\n"
            "<i>/cancel — отменить</i>"
        ),
        "cancelled": "Отменено.",
        "quick_alert.invalid": (
            "Неверный формат. Примеры:\n"
            "<code>&gt; 50000</code>\n"
            "<code>&lt; 1000</code>\n\n"
            "<i>/cancel — отменить</i>"
        ),
        "quick_alert.invalid_price": "Неверное значение цены. Попробуй ещё раз.",
        "quick_alert.limit": (
            "Достигнут лимит алертов (10).\n"
            "Удали старые через /unalert <ID>, список — /alerts"
        ),
        "quick_alert.created": (
            "✅ Алерт создан [ID {alert_id}]:\n"
            "<b>{ticker}</b> {sign} {threshold} на {exchange}\n"
            "Проверка каждые 5 минут."
        ),
    }
    en = {
        "ticker_unknown": "Ticker could not be recognized",
        "watch_done": "{ticker} added to favorites",
        "invalid_event_id": "Invalid event id",
        "event_missing": "Event not found",
        "track_exists": "Tracking is already enabled",
        "track_done": "Tracking enabled: reports in 15m, 1h, 4h and 24h",
        "exchange_unknown": "Exchange could not be recognized",
        "mute_ticker_done": "{ticker} muted",
        "mute_exchange_done": "{exchange} muted",
        "mute_ticker_alert": "🔕 {ticker} muted — listings for this coin will no longer arrive",
        "mute_exchange_alert": "🔕 {exchange} muted — listings from this exchange will no longer arrive",
        "quick_alert.price_hint": "\nCurrent price: <b>${price}</b>",
        "quick_alert.prompt": (
            "🔔 Alert for <b>{ticker}</b> on {exchange}{price_hint}\n\n"
            "Enter the trigger threshold:\n"
            "<code>&gt; 50000</code> — notify when the price rises above\n"
            "<code>&lt; 1000</code> — notify when the price falls below\n\n"
            "<i>/cancel — cancel</i>"
        ),
        "cancelled": "Cancelled.",
        "quick_alert.invalid": (
            "Invalid format. Examples:\n"
            "<code>&gt; 50000</code>\n"
            "<code>&lt; 1000</code>\n\n"
            "<i>/cancel — cancel</i>"
        ),
        "quick_alert.invalid_price": "Invalid price value. Try again.",
        "quick_alert.limit": (
            "Alert limit reached (10).\n"
            "Delete old ones via /unalert <ID>; list them with /alerts"
        ),
        "quick_alert.created": (
            "✅ Alert created [ID {alert_id}]:\n"
            "<b>{ticker}</b> {sign} {threshold} on {exchange}\n"
            "Checked every 5 minutes."
        ),
    }
    text = (en if lang == "en" else ru)[key]
    return text.format(**kwargs) if kwargs else text


async def _log_callback_click(
    session: AsyncSession,
    *,
    user_id: int,
    button_id: str,
    event: Event | None = None,
    exchange: str | None = None,
    market_type: str | None = None,
    properties: dict[str, Any] | None = None,
) -> None:
    await analytics_repo.log_event(
        session,
        event_name="callback_click",
        source="callback",
        user_id=user_id,
        event_id=(event.id if event is not None else None),
        exchange=(event.exchange if event is not None else exchange),
        market_type=(event.market_type.value if event is not None else market_type),
        placement="listing_notification",
        button_id=button_id,
        properties=properties or {},
    )


def _lang_from_user_settings(
    user_settings: dict | None,
    telegram_lang_code: str | None,
) -> str:
    return preferred_lang(user_settings, telegram_lang_code=telegram_lang_code)


@router.callback_query(WatchCB.filter())
async def cb_watch(
    callback: CallbackQuery,
    callback_data: WatchCB,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if callback.from_user is None:
        return
    ticker = callback_data.ticker.strip().upper()
    if not ticker:
        await callback.answer(_text("ticker_unknown", "ru"), show_alert=True)
        return

    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, callback.from_user.id, settings)
        lang = _lang_from_user_settings(user.settings, callback.from_user.language_code)
        await watchlist_repo.add_watch(session, user.id, ticker)
        await _log_callback_click(
            session,
            user_id=user.id,
            button_id="watch",
            properties={"ticker": ticker},
        )
        await session.commit()
    await callback.answer(_text("watch_done", lang, ticker=ticker))


@router.callback_query(TrackCB.filter())
async def cb_track(
    callback: CallbackQuery,
    callback_data: TrackCB,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    tracker_service: TrackerService,
) -> None:
    if callback.from_user is None:
        return
    try:
        event_id = uuid.UUID(callback_data.event_id)
    except ValueError:
        await callback.answer(_text("invalid_event_id", "en"), show_alert=True)
        return

    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, callback.from_user.id, settings)
        lang = _lang_from_user_settings(user.settings, callback.from_user.language_code)
        event = await events_repo.get_event(session, event_id)
        if event is None:
            await session.commit()
            await callback.answer(_text("event_missing", lang), show_alert=True)
            return
        scheduled = await tracker_service.subscribe_24h(session, user.id, event)
        await _log_callback_click(
            session,
            user_id=user.id,
            button_id="track",
            event=event,
            properties={"scheduled_reports": scheduled},
        )
        await session.commit()

    if not scheduled:
        await callback.answer(_text("track_exists", lang))
        return
    await callback.answer(_text("track_done", lang))


@router.callback_query(MuteTickerCB.filter())
async def cb_mute_ticker(
    callback: CallbackQuery,
    callback_data: MuteTickerCB,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if callback.from_user is None:
        return
    ticker = callback_data.ticker.strip().lower()
    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, callback.from_user.id, settings)
        lang = _lang_from_user_settings(user.settings, callback.from_user.language_code)
        if not ticker:
            await session.commit()
            await callback.answer(_text("ticker_unknown", lang), show_alert=True)
            return
        await mutes_repo.add_mute(session, user.id, MuteType.TICKER, ticker)
        await _log_callback_click(
            session,
            user_id=user.id,
            button_id="mute_ticker",
            properties={"ticker": ticker},
        )
        await session.commit()
    await callback.answer(_text("mute_ticker_done", lang, ticker=ticker.upper()))


@router.callback_query(MuteExchangeCB.filter())
async def cb_mute_exchange(
    callback: CallbackQuery,
    callback_data: MuteExchangeCB,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if callback.from_user is None:
        return
    exchange = callback_data.exchange.strip().lower()
    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, callback.from_user.id, settings)
        lang = _lang_from_user_settings(user.settings, callback.from_user.language_code)
        if not exchange:
            await session.commit()
            await callback.answer(_text("exchange_unknown", lang), show_alert=True)
            return
        await mutes_repo.add_mute(session, user.id, MuteType.EXCHANGE, exchange)
        await _log_callback_click(
            session,
            user_id=user.id,
            button_id="mute_exchange",
            properties={"exchange": exchange},
        )
        await session.commit()
    await callback.answer(
        _text("mute_exchange_done", lang, exchange=exchange.capitalize())
    )


@router.callback_query(MuteMenuCB.filter())
async def cb_mute_menu(
    callback: CallbackQuery,
    callback_data: MuteMenuCB,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    try:
        event_id = uuid.UUID(callback_data.event_id)
    except ValueError:
        await callback.answer()
        return

    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, callback.from_user.id, settings)
        lang = _lang_from_user_settings(user.settings, callback.from_user.language_code)
        event = await events_repo.get_event(session, event_id)
        await session.commit()

    if event is None:
        await callback.answer(_text("event_missing", lang), show_alert=True)
        return
    await callback.message.edit_reply_markup(reply_markup=build_mute_submenu(event, lang))
    await callback.answer()


@router.callback_query(MuteMenuBackCB.filter())
async def cb_mute_menu_back(
    callback: CallbackQuery,
    callback_data: MuteMenuBackCB,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    try:
        event_id = uuid.UUID(callback_data.event_id)
    except ValueError:
        await callback.answer()
        return

    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, callback.from_user.id, settings)
        lang = _lang_from_user_settings(user.settings, callback.from_user.language_code)
        event = await events_repo.get_event(session, event_id)
        await session.commit()

    if event is None:
        await callback.answer()
        return
    await callback.message.edit_reply_markup(reply_markup=build_event_actions(event, lang))
    await callback.answer()


@router.callback_query(SubMuteTickerCB.filter())
async def cb_sub_mute_ticker(
    callback: CallbackQuery,
    callback_data: SubMuteTickerCB,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    ticker = callback_data.ticker.strip().lower()
    try:
        event_id = uuid.UUID(callback_data.event_id)
    except ValueError:
        await callback.answer()
        return

    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, callback.from_user.id, settings)
        lang = _lang_from_user_settings(user.settings, callback.from_user.language_code)
        event = await events_repo.get_event(session, event_id)
        await mutes_repo.add_mute(session, user.id, MuteType.TICKER, ticker)
        await _log_callback_click(
            session,
            user_id=user.id,
            button_id="mute_ticker",
            event=event,
            properties={"ticker": ticker, "submenu": True},
        )
        await session.commit()

    if event is not None:
        await callback.message.edit_reply_markup(reply_markup=build_event_actions(event, lang))
    await callback.answer(
        _text("mute_ticker_alert", lang, ticker=ticker.upper()),
        show_alert=True,
    )


@router.callback_query(SubMuteExchangeCB.filter())
async def cb_sub_mute_exchange(
    callback: CallbackQuery,
    callback_data: SubMuteExchangeCB,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    exchange = callback_data.exchange.strip().lower()
    try:
        event_id = uuid.UUID(callback_data.event_id)
    except ValueError:
        await callback.answer()
        return

    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, callback.from_user.id, settings)
        lang = _lang_from_user_settings(user.settings, callback.from_user.language_code)
        event = await events_repo.get_event(session, event_id)
        await mutes_repo.add_mute(session, user.id, MuteType.EXCHANGE, exchange)
        await _log_callback_click(
            session,
            user_id=user.id,
            button_id="mute_exchange",
            event=event,
            properties={"exchange": exchange, "submenu": True},
        )
        await session.commit()

    if event is not None:
        await callback.message.edit_reply_markup(reply_markup=build_event_actions(event, lang))
    await callback.answer(
        _text("mute_exchange_alert", lang, exchange=exchange.capitalize()),
        show_alert=True,
    )


@router.callback_query(QuickAlertCB.filter())
async def cb_quick_alert(
    callback: CallbackQuery,
    callback_data: QuickAlertCB,
    session_factory: async_sessionmaker[AsyncSession],
    state: FSMContext,
    settings: Settings,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return

    ticker = callback_data.ticker.upper()
    exchange = callback_data.exchange.lower()
    event: Event | None = None
    price_hint = ""
    lang = "ru"

    try:
        event_id = uuid.UUID(callback_data.event_id)
        async with session_factory() as session:
            user = await users_repo.get_or_create_user(session, callback.from_user.id, settings)
            lang = _lang_from_user_settings(user.settings, callback.from_user.language_code)
            event = await events_repo.get_event(session, event_id)
            if event and event.enriched:
                price = event.enriched.get("price")
                if price is not None:
                    price_hint = _text("quick_alert.price_hint", lang, price=price)
            await _log_callback_click(
                session,
                user_id=user.id,
                button_id="alert_quick",
                event=event,
                exchange=exchange,
                market_type="spot",
                properties={"ticker": ticker},
            )
            await session.commit()
    except Exception:
        pass

    await state.set_state(QuickAlertState.waiting_price)
    await state.update_data(ticker=ticker, exchange=exchange, lang=lang)
    await callback.message.answer(
        _text(
            "quick_alert.prompt",
            lang,
            ticker=ticker,
            exchange=exchange.capitalize(),
            price_hint=price_hint,
        )
    )
    await callback.answer()


@router.message(Command("cancel"), QuickAlertState.waiting_price)
async def cancel_quick_alert(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = str(data.get("lang") or ("en" if message.from_user and (message.from_user.language_code or "").startswith("en") else "ru"))
    await state.clear()
    await message.answer(_text("cancelled", lang))


@router.message(QuickAlertState.waiting_price)
async def handle_quick_alert_price(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if message.from_user is None:
        return

    raw = (message.text or "").strip()
    data = await state.get_data()
    lang = str(data.get("lang") or "ru")
    match = _ALERT_PRICE_RE.match(raw)
    if not match:
        await message.answer(_text("quick_alert.invalid", lang))
        return

    direction = "gt" if match.group(1) == ">" else "lt"
    try:
        threshold = Decimal(match.group(2))
    except InvalidOperation:
        await message.answer(_text("quick_alert.invalid_price", lang))
        return

    ticker = str(data.get("ticker", ""))
    exchange = str(data.get("exchange", "binance"))

    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, message.from_user.id, settings)
        lang = _lang_from_user_settings(user.settings, message.from_user.language_code)
        alert = await alerts_repo.create_alert(
            session=session,
            user_id=user.id,
            ticker=ticker,
            direction=direction,
            threshold=threshold,
            exchange=exchange,
        )
        await session.commit()

    await state.clear()

    if alert is None:
        await message.answer(_text("quick_alert.limit", lang))
        return

    sign = ">" if direction == "gt" else "<"
    await message.answer(
        _text(
            "quick_alert.created",
            lang,
            alert_id=alert.id,
            ticker=ticker,
            sign=sign,
            threshold=threshold,
            exchange=exchange.capitalize(),
        )
    )
