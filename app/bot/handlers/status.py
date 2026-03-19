from __future__ import annotations

from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot.lang import preferred_lang
from app.config import Settings
from app.db.repo import events as events_repo
from app.db.repo import mutes as mutes_repo
from app.db.repo import price_alerts as alerts_repo
from app.db.repo import users as users_repo
from app.db.repo import watchlist as watchlist_repo
from app.services.filtering import normalize_filters

router = Router()


def _pause_status(user_settings: dict, lang: str) -> str:
    paused_until = user_settings.get("paused_until")
    none_text = "none" if lang == "en" else "нет"
    if not paused_until:
        return none_text
    try:
        dt = datetime.fromisoformat(paused_until)
    except ValueError:
        return none_text
    if dt <= datetime.now(timezone.utc):
        return none_text
    prefix = "until" if lang == "en" else "до"
    return f"{prefix} {dt.strftime('%H:%M UTC %d %b')}"


@router.message(Command("status"))
async def cmd_status(
    message: Message,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return

    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, message.from_user.id, settings)
        user_settings = user.settings or {}
        lang = preferred_lang(
            user_settings,
            telegram_lang_code=message.from_user.language_code,
        )
        filters = normalize_filters(user_settings, settings)
        watchlist = await watchlist_repo.list_watchlist(session, user.id)
        mutes = await mutes_repo.list_mutes(session, user.id)
        active_alerts = await alerts_repo.list_active_alerts(session, user.id)
        events_24h = await events_repo.count_events_last_hours(session, 24)
        await session.commit()

    digest_on = bool(user_settings.get("digest_mode", False))
    pause_str = _pause_status(user_settings, lang)

    if lang == "en":
        text = (
            "<b>Bot status</b>\n\n"
            f"Events over 24h: {events_24h}\n\n"
            "<b>Filters:</b>\n"
            f"Exchanges: {', '.join(sorted(filters.enabled_exchanges))}\n"
            f"Markets: {', '.join(sorted(filters.enabled_market_types))}\n"
            f"USDT only: {filters.only_usdt}\n"
            f"Min score: {filters.min_score}\n\n"
            "<b>Notifications:</b>\n"
            f"Pause: {pause_str}\n"
            f"Digest: {'on' if digest_on else 'off'}\n\n"
            f"<b>Watchlist</b> ({len(watchlist)}): "
            f"{', '.join(watchlist) if watchlist else '—'}\n"
            f"<b>Mutes:</b> {len(mutes)}\n"
            f"<b>Alerts:</b> {len(active_alerts)} active"
        )
    else:
        text = (
            "<b>Статус бота</b>\n\n"
            f"События за 24ч: {events_24h}\n\n"
            "<b>Фильтры:</b>\n"
            f"Биржи: {', '.join(sorted(filters.enabled_exchanges))}\n"
            f"Рынки: {', '.join(sorted(filters.enabled_market_types))}\n"
            f"Только USDT: {filters.only_usdt}\n"
            f"Min score: {filters.min_score}\n\n"
            "<b>Уведомления:</b>\n"
            f"Пауза: {pause_str}\n"
            f"Дайджест: {'вкл' if digest_on else 'выкл'}\n\n"
            f"<b>Watchlist</b> ({len(watchlist)}): "
            f"{', '.join(watchlist) if watchlist else '—'}\n"
            f"<b>Мьюты:</b> {len(mutes)}\n"
            f"<b>Алерты:</b> {len(active_alerts)} активных"
        )
    await message.answer(text)
