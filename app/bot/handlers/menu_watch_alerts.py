from __future__ import annotations

from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.callback_data import MenuActionCB
from app.bot.handlers.menu_shared import (
    MenuFSM,
    _ALERT_RE,
    _KNOWN_EXCHANGES,
    _TICKER_RE,
)
from app.bot.keyboards.main_menu import build_cancel_keyboard
from app.bot.lang import preferred_lang
from app.config import Settings
from app.db.repo import price_alerts as alerts_repo
from app.db.repo import users as users_repo
from app.db.repo import watchlist as watchlist_repo

router = Router()


def _text(key: str, lang: str, **kwargs: str | int | Decimal) -> str:
    ru = {
        "watchlist.empty": "📋 <b>Watchlist:</b> —",
        "watchlist.header": "📋 <b>Watchlist:</b> {items}",
        "watch.add.prompt": (
            "Введите тикер монеты для добавления в watchlist\n"
            "Пример: <code>BTC</code>"
        ),
        "watch.remove.prompt": (
            "Введите тикер монеты для удаления из watchlist\n"
            "Пример: <code>BTC</code>"
        ),
        "watch.invalid.add": (
            "Неверный тикер. Только буквы и цифры, до 16 символов.\n"
            "Пример: <code>BTC</code>"
        ),
        "watch.invalid.remove": "Неверный тикер. Пример: <code>BTC</code>",
        "watch.added": "✅ {ticker} добавлен в watchlist",
        "watch.removed": "✅ {ticker} удалён из watchlist",
        "watch.missing": "{ticker} не найден в watchlist",
        "alerts.empty": "Нет активных алертов. Нажми «➕ Новый алерт» для создания.",
        "alerts.header": "📋 <b>Активные алерты:</b>",
        "alerts.footer": "\nДля удаления нажми «❌ Удалить алерт»",
        "alert.add.prompt": (
            "Введите алерт в формате: <code>TICKER >|< ЦЕНА [биржа]</code>\n\n"
            "Примеры:\n"
            "<code>BTC > 50000</code>\n"
            "<code>ETH < 2000 bybit</code>"
        ),
        "alert.remove.prompt": (
            "Введите ID алерта для удаления\n"
            "ID можно найти в списке (кнопка «📋 Мои алерты»)"
        ),
        "alert.invalid": "Неверный формат. Пример: <code>BTC > 50000</code>",
        "alert.invalid_price": "Неверное значение цены.",
        "alert.unknown_exchange": (
            "Неизвестная биржа: {exchange}. Доступны: binance, bybit"
        ),
        "alert.limit": (
            "Достигнут лимит алертов (10). Удали старые через кнопку "
            "«❌ Удалить алерт»."
        ),
        "alert.created": (
            "✅ Алерт создан [ID {alert_id}]:\n"
            "{ticker}/USDT {sign} {threshold} на {exchange}\n"
            "Проверка каждые 5 минут."
        ),
        "alert.id.invalid": "Введите числовой ID алерта.",
        "alert.deleted": "✅ Алерт [{alert_id}] удалён.",
        "alert.missing": "Алерт [{alert_id}] не найден или уже неактивен.",
    }
    en = {
        "watchlist.empty": "📋 <b>Watchlist:</b> —",
        "watchlist.header": "📋 <b>Watchlist:</b> {items}",
        "watch.add.prompt": (
            "Enter the ticker to add to your watchlist\n"
            "Example: <code>BTC</code>"
        ),
        "watch.remove.prompt": (
            "Enter the ticker to remove from your watchlist\n"
            "Example: <code>BTC</code>"
        ),
        "watch.invalid.add": (
            "Invalid ticker. Use letters and digits only, up to 16 characters.\n"
            "Example: <code>BTC</code>"
        ),
        "watch.invalid.remove": "Invalid ticker. Example: <code>BTC</code>",
        "watch.added": "✅ {ticker} added to the watchlist",
        "watch.removed": "✅ {ticker} removed from the watchlist",
        "watch.missing": "{ticker} is not in the watchlist",
        "alerts.empty": "No active alerts. Tap “➕ New alert” to create one.",
        "alerts.header": "📋 <b>Active alerts:</b>",
        "alerts.footer": "\nTo delete one, tap “❌ Delete alert”",
        "alert.add.prompt": (
            "Enter an alert in the format: <code>TICKER >|< PRICE [exchange]</code>\n\n"
            "Examples:\n"
            "<code>BTC > 50000</code>\n"
            "<code>ETH < 2000 bybit</code>"
        ),
        "alert.remove.prompt": (
            "Enter the alert ID to delete\n"
            "You can find it in the list via “📋 My alerts”"
        ),
        "alert.invalid": "Invalid format. Example: <code>BTC > 50000</code>",
        "alert.invalid_price": "Invalid price value.",
        "alert.unknown_exchange": "Unknown exchange: {exchange}. Available: binance, bybit",
        "alert.limit": "Alert limit reached (10). Delete old ones via “❌ Delete alert”.",
        "alert.created": (
            "✅ Alert created [ID {alert_id}]:\n"
            "{ticker}/USDT {sign} {threshold} on {exchange}\n"
            "Checked every 5 minutes."
        ),
        "alert.id.invalid": "Enter a numeric alert ID.",
        "alert.deleted": "✅ Alert [{alert_id}] deleted.",
        "alert.missing": "Alert [{alert_id}] was not found or is already inactive.",
    }
    text = (en if lang == "en" else ru)[key]
    return text.format(**kwargs) if kwargs else text


async def _load_user_lang(
    user_id: int,
    telegram_lang_code: str | None,
    session: AsyncSession,
    settings: Settings,
) -> tuple[str, int]:
    user = await users_repo.get_or_create_user(session, user_id, settings)
    return preferred_lang(user.settings, telegram_lang_code=telegram_lang_code), user.id


@router.callback_query(MenuActionCB.filter(F.action == "watchlist"))
async def cb_menu_watchlist(
    callback: CallbackQuery,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    async with session_factory() as session:
        lang, user_id = await _load_user_lang(
            callback.from_user.id,
            callback.from_user.language_code,
            session,
            settings,
        )
        items = await watchlist_repo.list_watchlist(session, user_id)
        await session.commit()
    text = (
        _text("watchlist.header", lang, items=", ".join(items))
        if items
        else _text("watchlist.empty", lang)
    )
    await callback.message.answer(text)
    await callback.answer()


@router.callback_query(MenuActionCB.filter(F.action == "watch_add"))
async def cb_menu_watch_add(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    async with session_factory() as session:
        lang, _ = await _load_user_lang(
            callback.from_user.id,
            callback.from_user.language_code,
            session,
            settings,
        )
    await state.set_state(MenuFSM.watch_add)
    await callback.message.answer(
        _text("watch.add.prompt", lang),
        reply_markup=build_cancel_keyboard(lang),
    )
    await callback.answer()


@router.callback_query(MenuActionCB.filter(F.action == "watch_remove"))
async def cb_menu_watch_remove(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    async with session_factory() as session:
        lang, _ = await _load_user_lang(
            callback.from_user.id,
            callback.from_user.language_code,
            session,
            settings,
        )
    await state.set_state(MenuFSM.watch_remove)
    await callback.message.answer(
        _text("watch.remove.prompt", lang),
        reply_markup=build_cancel_keyboard(lang),
    )
    await callback.answer()


@router.message(MenuFSM.watch_add)
async def fsm_watch_add(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if message.from_user is None:
        return
    async with session_factory() as session:
        lang, user_id = await _load_user_lang(
            message.from_user.id,
            message.from_user.language_code,
            session,
            settings,
        )
        ticker = (message.text or "").strip().upper()
        if not _TICKER_RE.match(ticker):
            await message.answer(
                _text("watch.invalid.add", lang),
                reply_markup=build_cancel_keyboard(lang),
            )
            await session.commit()
            return
        await watchlist_repo.add_watch(session, user_id, ticker)
        await session.commit()
    await state.clear()
    await message.answer(_text("watch.added", lang, ticker=ticker))


@router.message(MenuFSM.watch_remove)
async def fsm_watch_remove(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if message.from_user is None:
        return
    async with session_factory() as session:
        lang, user_id = await _load_user_lang(
            message.from_user.id,
            message.from_user.language_code,
            session,
            settings,
        )
        ticker = (message.text or "").strip().upper()
        if not _TICKER_RE.match(ticker):
            await message.answer(
                _text("watch.invalid.remove", lang),
                reply_markup=build_cancel_keyboard(lang),
            )
            await session.commit()
            return
        removed = await watchlist_repo.remove_watch(session, user_id, ticker)
        await session.commit()
    await state.clear()
    if removed:
        await message.answer(_text("watch.removed", lang, ticker=ticker))
    else:
        await message.answer(_text("watch.missing", lang, ticker=ticker))


@router.callback_query(MenuActionCB.filter(F.action == "alerts_list"))
async def cb_menu_alerts_list(
    callback: CallbackQuery,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    async with session_factory() as session:
        lang, user_id = await _load_user_lang(
            callback.from_user.id,
            callback.from_user.language_code,
            session,
            settings,
        )
        active = await alerts_repo.list_active_alerts(session, user_id)
        await session.commit()
    if not active:
        await callback.message.answer(_text("alerts.empty", lang))
        await callback.answer()
        return
    lines = [_text("alerts.header", lang)]
    for alert in active:
        sign = ">" if alert.direction == "gt" else "<"
        exchange = (alert.exchange or "binance").capitalize()
        lines.append(f"[{alert.id}] {alert.ticker}/USDT {sign} {alert.threshold} — {exchange}")
    lines.append(_text("alerts.footer", lang))
    await callback.message.answer("\n".join(lines))
    await callback.answer()


@router.callback_query(MenuActionCB.filter(F.action == "alert_add"))
async def cb_menu_alert_add(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    async with session_factory() as session:
        lang, _ = await _load_user_lang(
            callback.from_user.id,
            callback.from_user.language_code,
            session,
            settings,
        )
    await state.set_state(MenuFSM.alert_add)
    await callback.message.answer(
        _text("alert.add.prompt", lang),
        reply_markup=build_cancel_keyboard(lang),
    )
    await callback.answer()


@router.callback_query(MenuActionCB.filter(F.action == "unalert"))
async def cb_menu_unalert(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    async with session_factory() as session:
        lang, _ = await _load_user_lang(
            callback.from_user.id,
            callback.from_user.language_code,
            session,
            settings,
        )
    await state.set_state(MenuFSM.unalert)
    await callback.message.answer(
        _text("alert.remove.prompt", lang),
        reply_markup=build_cancel_keyboard(lang),
    )
    await callback.answer()


@router.message(MenuFSM.alert_add)
async def fsm_alert_add(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if message.from_user is None:
        return
    raw = (message.text or "").strip()
    async with session_factory() as session:
        lang, user_id = await _load_user_lang(
            message.from_user.id,
            message.from_user.language_code,
            session,
            settings,
        )
        match = _ALERT_RE.match(raw)
        if not match:
            await message.answer(
                _text("alert.invalid", lang),
                reply_markup=build_cancel_keyboard(lang),
            )
            await session.commit()
            return
        ticker = match.group(1).upper()
        direction = "gt" if match.group(2) == ">" else "lt"
        try:
            threshold = Decimal(match.group(3))
        except InvalidOperation:
            await message.answer(
                _text("alert.invalid_price", lang),
                reply_markup=build_cancel_keyboard(lang),
            )
            await session.commit()
            return
        exchange_raw = (match.group(4) or "binance").strip().lower()
        if exchange_raw not in _KNOWN_EXCHANGES:
            await message.answer(
                _text("alert.unknown_exchange", lang, exchange=exchange_raw),
                reply_markup=build_cancel_keyboard(lang),
            )
            await session.commit()
            return
        alert = await alerts_repo.create_alert(
            session=session,
            user_id=user_id,
            ticker=ticker,
            direction=direction,
            threshold=threshold,
            exchange=exchange_raw,
        )
        await session.commit()
    await state.clear()
    if alert is None:
        await message.answer(_text("alert.limit", lang))
        return
    sign = ">" if direction == "gt" else "<"
    await message.answer(
        _text(
            "alert.created",
            lang,
            alert_id=alert.id,
            ticker=ticker,
            sign=sign,
            threshold=threshold,
            exchange=exchange_raw.capitalize(),
        )
    )


@router.message(MenuFSM.unalert)
async def fsm_unalert(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if message.from_user is None:
        return
    async with session_factory() as session:
        lang, user_id = await _load_user_lang(
            message.from_user.id,
            message.from_user.language_code,
            session,
            settings,
        )
        raw = (message.text or "").strip()
        if not raw.isdigit():
            await message.answer(
                _text("alert.id.invalid", lang),
                reply_markup=build_cancel_keyboard(lang),
            )
            await session.commit()
            return
        alert_id = int(raw)
        removed = await alerts_repo.deactivate_alert(session, user_id, alert_id)
        await session.commit()
    await state.clear()
    if removed:
        await message.answer(_text("alert.deleted", lang, alert_id=alert_id))
    else:
        await message.answer(_text("alert.missing", lang, alert_id=alert_id))
