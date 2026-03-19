from __future__ import annotations

import csv
import io
import math
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.callback_data import HistoryPageCB, MenuActionCB
from app.bot.handlers.menu_shared import _BAR_WIDTH, _MARKET_EMOJI, _PAGE_SIZE, _PERIODS
from app.bot.lang import preferred_lang
from app.config import Settings
from app.db.models import Event
from app.db.repo import events as events_repo
from app.db.repo import mutes as mutes_repo
from app.db.repo import price_alerts as alerts_repo
from app.db.repo import users as users_repo
from app.db.repo import watchlist as watchlist_repo
from app.i18n import t
from app.services.filtering import normalize_filters

router = Router()


def _text(key: str, lang: str, **kwargs: str | int) -> str:
    ru = {
        "loading": "Загружаю...",
        "building": "Формирую файл...",
        "analytics.header": "📊 <b>Статистика листингов</b>\n",
        "analytics.empty_period": "<b>За {label}:</b> нет данных\n",
        "analytics.period": "<b>За {label}</b> (всего {total}):",
        "top.empty": "За последние 24 часа новых листингов не обнаружено.",
        "top.header": "🏆 <b>Топ листингов за 24 часа</b>\n",
        "history.header": "📋 История листингов — стр. 1/{total_pages} (всего {total})\n",
        "history.empty": "Пока нет листингов.",
        "history.next": "Next ▶",
        "export.empty": "За последние 7 дней листингов не найдено.",
        "export.caption": "📥 Листинги за последние 7 дней — {count} записей",
        "pause.none": "нет",
        "pause.until": "до {value}",
        "status.header": "<b>Статус бота</b>\n\n",
        "status.events": "События за 24ч: {count}\n\n",
        "status.filters": "<b>Фильтры:</b>\n",
        "status.exchanges": "Биржи: {value}\n",
        "status.markets": "Рынки: {value}\n",
        "status.usdt": "Только USDT: {value}\n",
        "status.score": "Min score: {value}\n\n",
        "status.notifications": "<b>Уведомления:</b>\n",
        "status.pause": "Пауза: {value}\n",
        "status.digest": "Дайджест: {value}\n\n",
        "status.watchlist": "<b>Watchlist</b> ({count}): {items}\n",
        "status.mutes": "<b>Мьюты:</b> {count}\n",
        "status.alerts": "<b>Алерты:</b> {count} активных",
        "status.digest.on": "вкл",
        "status.digest.off": "выкл",
    }
    en = {
        "loading": "Loading...",
        "building": "Building file...",
        "analytics.header": "📊 <b>Listing stats</b>\n",
        "analytics.empty_period": "<b>For {label}:</b> no data\n",
        "analytics.period": "<b>For {label}</b> (total {total}):",
        "top.empty": "No new listings were detected over the last 24 hours.",
        "top.header": "🏆 <b>Top listings over 24 hours</b>\n",
        "history.header": "📋 Listing history — page 1/{total_pages} (total {total})\n",
        "history.empty": "No listings yet.",
        "history.next": "Next ▶",
        "export.empty": "No listings found over the last 7 days.",
        "export.caption": "📥 Listings from the last 7 days — {count} rows",
        "pause.none": "none",
        "pause.until": "until {value}",
        "status.header": "<b>Bot status</b>\n\n",
        "status.events": "Events over 24h: {count}\n\n",
        "status.filters": "<b>Filters:</b>\n",
        "status.exchanges": "Exchanges: {value}\n",
        "status.markets": "Markets: {value}\n",
        "status.usdt": "USDT only: {value}\n",
        "status.score": "Min score: {value}\n\n",
        "status.notifications": "<b>Notifications:</b>\n",
        "status.pause": "Pause: {value}\n",
        "status.digest": "Digest: {value}\n\n",
        "status.watchlist": "<b>Watchlist</b> ({count}): {items}\n",
        "status.mutes": "<b>Mutes:</b> {count}\n",
        "status.alerts": "<b>Alerts:</b> {count} active",
        "status.digest.on": "on",
        "status.digest.off": "off",
    }
    text = (en if lang == "en" else ru)[key]
    return text.format(**kwargs) if kwargs else text


def _bar(value: int, max_value: int) -> str:
    if max_value == 0:
        return "░" * _BAR_WIDTH
    filled = round(_BAR_WIDTH * value / max_value)
    return "█" * filled + "░" * (_BAR_WIDTH - filled)


async def _count_for_period(
    session: AsyncSession,
    since: datetime,
) -> dict[str, dict[str, int]]:
    result = await session.execute(
        select(
            Event.exchange,
            Event.market_type,
            func.count(Event.id).label("cnt"),
        )
        .where(Event.first_seen_at >= since)
        .group_by(Event.exchange, Event.market_type)
    )
    data: dict[str, dict[str, int]] = {}
    for exchange, market_type, count in result.fetchall():
        data.setdefault(exchange, {})[market_type.value] = count
    return data


async def _resolve_lang(
    session: AsyncSession,
    user_id: int,
    telegram_lang_code: str | None,
    settings: Settings,
) -> str:
    user = await users_repo.get_or_create_user(session, user_id, settings)
    return preferred_lang(user.settings, telegram_lang_code=telegram_lang_code)


@router.callback_query(MenuActionCB.filter(F.action == "analytics"))
async def cb_menu_analytics(
    callback: CallbackQuery,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    async with session_factory() as session:
        lang = await _resolve_lang(
            session,
            callback.from_user.id,
            callback.from_user.language_code,
            settings,
        )
        await callback.answer(_text("loading", lang))
        now = datetime.now(timezone.utc)
        sections: list[str] = [_text("analytics.header", lang)]
        for label, delta in _PERIODS:
            since = now - delta
            data = await _count_for_period(session, since)
            if not data:
                sections.append(_text("analytics.empty_period", lang, label=label))
                continue
            rows: list[tuple[str, str, int]] = []
            for exchange, markets in sorted(data.items()):
                for market_type, count in sorted(markets.items()):
                    rows.append((exchange.capitalize(), market_type, count))
            max_count = max(count for _, _, count in rows)
            total = sum(count for _, _, count in rows)
            lines = [_text("analytics.period", lang, label=label, total=total)]
            for exchange, market_type, count in rows:
                lines.append(f"  {exchange} {market_type}: {_bar(count, max_count)} {count}")
            sections.append("\n".join(lines) + "\n")
        await session.commit()
    await callback.message.answer("\n".join(sections))


@router.callback_query(MenuActionCB.filter(F.action == "top"))
async def cb_menu_top(
    callback: CallbackQuery,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    async with session_factory() as session:
        lang = await _resolve_lang(
            session,
            callback.from_user.id,
            callback.from_user.language_code,
            settings,
        )
        await callback.answer(_text("loading", lang))
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        result = await session.execute(
            select(Event)
            .where(Event.first_seen_at >= since)
            .order_by(Event.score.desc(), Event.first_seen_at.desc())
            .limit(10)
        )
        events = list(result.scalars())
        await session.commit()
    if not events:
        await callback.message.answer(_text("top.empty", lang))
        return
    lines = [_text("top.header", lang)]
    for index, event in enumerate(events, 1):
        market_emoji = _MARKET_EMOJI.get(event.market_type.value, "⚪")
        price = (event.enriched or {}).get("price")
        price_str = f" · ${price}" if price else ""
        lines.append(
            f"{index}. {market_emoji} <b>{event.symbol_base}/{event.symbol_quote}</b>"
            f" — {event.exchange.capitalize()}{price_str}\n"
            f"   Score: {event.score}/100 | {event.event_type.value.replace('_', ' ')}"
        )
    await callback.message.answer("\n".join(lines))


@router.callback_query(MenuActionCB.filter(F.action == "history"))
async def cb_menu_history(
    callback: CallbackQuery,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    async with session_factory() as session:
        lang = await _resolve_lang(
            session,
            callback.from_user.id,
            callback.from_user.language_code,
            settings,
        )
        await callback.answer(_text("loading", lang))
        events, total = await events_repo.list_events_page(session, page=0, exchange=None)
        await session.commit()
    total_pages = max(1, math.ceil(total / _PAGE_SIZE))
    header = _text("history.header", lang, total_pages=total_pages, total=total)
    if not events:
        await callback.message.answer(f"{header}\n{_text('history.empty', lang)}")
        return
    lines = [header]
    for event in events:
        timestamp = event.first_seen_at.strftime("%d.%m %H:%M")
        market = "Spot" if event.market_type.value == "spot" else "Futures"
        score = event.score or 0
        lines.append(
            f"• <b>{event.symbol_base}/{event.symbol_quote}</b> "
            f"{event.exchange.capitalize()} {market} | Score {score} | {timestamp} UTC"
        )
    nav_buttons: list[InlineKeyboardButton] = []
    if total > _PAGE_SIZE:
        nav_buttons.append(
            InlineKeyboardButton(
                text=_text("history.next", lang),
                callback_data=HistoryPageCB(page=1, exchange="").pack(),
            )
        )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[nav_buttons]) if nav_buttons else None
    await callback.message.answer("\n".join(lines), reply_markup=keyboard)


@router.callback_query(MenuActionCB.filter(F.action == "export"))
async def cb_menu_export(
    callback: CallbackQuery,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    async with session_factory() as session:
        lang = await _resolve_lang(
            session,
            callback.from_user.id,
            callback.from_user.language_code,
            settings,
        )
        await callback.answer(_text("building", lang))
        since = datetime.now(timezone.utc) - timedelta(days=7)
        result = await session.execute(
            select(Event)
            .where(Event.first_seen_at >= since)
            .order_by(Event.first_seen_at.desc())
            .limit(500)
        )
        events = list(result.scalars())
        await session.commit()
    if not events:
        await callback.message.answer(_text("export.empty", lang))
        return
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "date_utc",
            "exchange",
            "market_type",
            "event_type",
            "base",
            "quote",
            "score",
            "flags",
            "price",
            "volume_5m",
        ]
    )
    for event in events:
        enriched = event.enriched or {}
        writer.writerow(
            [
                event.first_seen_at.strftime("%Y-%m-%d %H:%M"),
                event.exchange,
                event.market_type.value,
                event.event_type.value,
                event.symbol_base,
                event.symbol_quote,
                event.score,
                "|".join(event.flags or []),
                enriched.get("price", ""),
                enriched.get("volume_5m", ""),
            ]
        )
    filename = f"listings_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    file_bytes = buffer.getvalue().encode("utf-8-sig")
    await callback.message.answer_document(
        BufferedInputFile(file_bytes, filename=filename),
        caption=_text("export.caption", lang, count=len(events)),
    )


@router.callback_query(MenuActionCB.filter(F.action == "help"))
async def cb_menu_help(
    callback: CallbackQuery,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    async with session_factory() as session:
        lang = await _resolve_lang(
            session,
            callback.from_user.id,
            callback.from_user.language_code,
            settings,
        )
        await session.commit()
    await callback.message.answer(t("help.text", lang))
    await callback.answer()


@router.callback_query(MenuActionCB.filter(F.action == "status"))
async def cb_menu_status(
    callback: CallbackQuery,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    async with session_factory() as session:
        lang = await _resolve_lang(
            session,
            callback.from_user.id,
            callback.from_user.language_code,
            settings,
        )
        await callback.answer(_text("loading", lang))
        user = await users_repo.get_or_create_user(session, callback.from_user.id, settings)
        user_settings = user.settings or {}
        filters = normalize_filters(user_settings, settings)
        watchlist = await watchlist_repo.list_watchlist(session, user.id)
        mutes = await mutes_repo.list_mutes(session, user.id)
        active_alerts = await alerts_repo.list_active_alerts(session, user.id)
        events_24h = await events_repo.count_events_last_hours(session, 24)
        await session.commit()
    digest_on = bool(user_settings.get("digest_mode", False))
    paused_until = user_settings.get("paused_until")
    pause_str = _text("pause.none", lang)
    if paused_until:
        try:
            dt = datetime.fromisoformat(paused_until)
            if dt > datetime.now(timezone.utc):
                pause_str = _text(
                    "pause.until",
                    lang,
                    value=dt.strftime("%H:%M UTC %d %b"),
                )
        except ValueError:
            pass
    text = (
        _text("status.header", lang)
        + _text("status.events", lang, count=events_24h)
        + _text("status.filters", lang)
        + _text("status.exchanges", lang, value=", ".join(sorted(filters.enabled_exchanges)))
        + _text("status.markets", lang, value=", ".join(sorted(filters.enabled_market_types)))
        + _text("status.usdt", lang, value=str(filters.only_usdt))
        + _text("status.score", lang, value=filters.min_score)
        + _text("status.notifications", lang)
        + _text("status.pause", lang, value=pause_str)
        + _text(
            "status.digest",
            lang,
            value=_text("status.digest.on", lang) if digest_on else _text("status.digest.off", lang),
        )
        + _text(
            "status.watchlist",
            lang,
            count=len(watchlist),
            items=", ".join(watchlist) if watchlist else "—",
        )
        + _text("status.mutes", lang, count=len(mutes))
        + _text("status.alerts", lang, count=len(active_alerts))
    )
    await callback.message.answer(text)
