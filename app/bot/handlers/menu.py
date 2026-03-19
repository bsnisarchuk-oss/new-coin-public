from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.callback_data import MenuActionCB
from app.bot.handlers import menu_insights, menu_watch_alerts
from app.bot.handlers.menu_shared import MenuFSM, _DURATION_RE
from app.bot.keyboards.filters_menu import build_filters_keyboard, render_filters_text
from app.bot.keyboards.main_menu import (
    build_alerts_section,
    build_analytics_section,
    build_cancel_keyboard,
    build_help_section,
    build_settings_section,
    build_watch_section,
)
from app.bot.lang import preferred_lang
from app.config import Settings
from app.db.repo import presets as presets_repo
from app.db.repo import users as users_repo
from app.i18n import t
from app.services.filtering import normalize_filters

router = Router()
router.include_router(menu_watch_alerts.router)
router.include_router(menu_insights.router)


def _section_filter(*values: str):  # noqa: ANN202
    return F.text.in_(set(values))


async def _resolve_lang(
    user_id: int,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    telegram_lang_code: str | None = None,
) -> str:
    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, user_id, settings)
        await session.commit()
    return preferred_lang(user.settings, telegram_lang_code=telegram_lang_code)


@router.message(_section_filter("👁 Слежка", "👁 Watch"))
async def section_watch(
    message: Message,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if message.from_user is None:
        return
    lang = await _resolve_lang(
        message.from_user.id,
        session_factory,
        settings,
        message.from_user.language_code,
    )
    await message.answer(
        t("menu.section.watch", lang),
        reply_markup=build_watch_section(lang),
    )


@router.message(_section_filter("🔔 Алерты", "🔔 Alerts"))
async def section_alerts(
    message: Message,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if message.from_user is None:
        return
    lang = await _resolve_lang(
        message.from_user.id,
        session_factory,
        settings,
        message.from_user.language_code,
    )
    await message.answer(
        t("menu.section.alerts", lang),
        reply_markup=build_alerts_section(lang),
    )


@router.message(_section_filter("⚙️ Настройки", "⚙️ Settings"))
async def section_settings(
    message: Message,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if message.from_user is None:
        return
    lang = await _resolve_lang(
        message.from_user.id,
        session_factory,
        settings,
        message.from_user.language_code,
    )
    await message.answer(
        t("menu.section.settings", lang),
        reply_markup=build_settings_section(lang),
    )


@router.message(_section_filter("📈 Аналитика", "📈 Analytics"))
async def section_analytics(
    message: Message,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if message.from_user is None:
        return
    lang = await _resolve_lang(
        message.from_user.id,
        session_factory,
        settings,
        message.from_user.language_code,
    )
    await message.answer(
        t("menu.section.analytics", lang),
        reply_markup=build_analytics_section(lang),
    )


@router.message(_section_filter("ℹ️ Помощь", "ℹ️ Help"))
async def section_help(
    message: Message,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if message.from_user is None:
        return
    lang = await _resolve_lang(
        message.from_user.id,
        session_factory,
        settings,
        message.from_user.language_code,
    )
    await message.answer(
        t("menu.section.help", lang),
        reply_markup=build_help_section(lang),
    )


@router.callback_query(MenuActionCB.filter(F.action == "close"))
async def cb_close(callback: CallbackQuery) -> None:
    if callback.message:
        await callback.message.delete()
    await callback.answer()


@router.callback_query(MenuActionCB.filter(F.action == "cancel_fsm"))
async def cb_cancel_fsm(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.delete()
    await callback.answer()


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current and current.startswith("MenuFSM:"):
        await state.clear()
        lang = (
            "en"
            if message.from_user and (message.from_user.language_code or "").startswith("en")
            else "ru"
        )
        await message.answer("Cancelled." if lang == "en" else "Отменено.")


@router.callback_query(MenuActionCB.filter(F.action == "filters"))
async def cb_menu_filters(
    callback: CallbackQuery,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, callback.from_user.id, settings)
        raw = dict(user.settings or {})
        lang = preferred_lang(
            user.settings,
            telegram_lang_code=callback.from_user.language_code,
        )
        await session.commit()
    filters = normalize_filters(raw, settings)
    await callback.message.answer(
        render_filters_text(filters, lang),
        reply_markup=build_filters_keyboard(filters, lang),
    )
    await callback.answer()


@router.callback_query(MenuActionCB.filter(F.action == "presets"))
async def cb_menu_presets(
    callback: CallbackQuery,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, callback.from_user.id, settings)
        all_presets = await presets_repo.list_presets(session, user.id)
        lang = preferred_lang(
            user.settings,
            telegram_lang_code=callback.from_user.language_code,
        )
        await session.commit()
    if not all_presets:
        text = (
            "No saved presets.\nCreate one with <code>/preset save name</code>"
            if lang == "en"
            else "Нет сохранённых пресетов.\nСоздай командой: <code>/preset save имя</code>"
        )
        await callback.message.answer(text)
    else:
        lines = (
            ["📁 <b>Filter presets:</b>"]
            if lang == "en"
            else ["📁 <b>Пресеты фильтров:</b>"]
        )
        for preset in all_presets:
            filters = normalize_filters(preset.settings, settings)
            exchanges = ",".join(sorted(filters.enabled_exchanges))
            market_types = ",".join(sorted(filters.enabled_market_types))
            lines.append(
                f"• <b>{preset.name}</b> | {exchanges} | {market_types} | "
                f"score≥{filters.min_score} | usdt={filters.only_usdt}"
            )
        lines.append(
            "\n<code>/preset load NAME</code> — apply"
            if lang == "en"
            else "\n<code>/preset load ИМЯ</code> — применить"
        )
        await callback.message.answer("\n".join(lines))
    await callback.answer()


@router.callback_query(MenuActionCB.filter(F.action == "pause"))
async def cb_menu_pause(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    lang = await _resolve_lang(
        callback.from_user.id,
        session_factory,
        settings,
        callback.from_user.language_code,
    )
    await state.set_state(MenuFSM.pause_set)
    text = (
        "Enter a pause duration: <code>30m</code>, <code>2h</code>, <code>1d</code>\n"
        "Or <code>0</code> to remove the current pause\n\n"
        "Maximum: 72h"
        if lang == "en"
        else "Введите длительность паузы: <code>30m</code>, <code>2h</code>, <code>1d</code>\n"
        "Или <code>0</code> чтобы снять текущую паузу\n\n"
        "Максимум: 72h"
    )
    await callback.message.answer(text, reply_markup=build_cancel_keyboard(lang))
    await callback.answer()


@router.message(MenuFSM.pause_set)
async def fsm_pause_set(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if message.from_user is None:
        return
    raw = (message.text or "").strip()
    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, message.from_user.id, settings)
        lang = preferred_lang(
            user.settings,
            telegram_lang_code=message.from_user.language_code,
        )
        if raw == "0":
            current = user.settings or {}
            if not current.get("paused_until"):
                await session.commit()
                await state.clear()
                await message.answer(
                    "Notifications are active, there is no pause."
                    if lang == "en"
                    else "Уведомления активны, паузы нет."
                )
                return
            user.settings = users_repo.merge_user_settings(current, {"paused_until": None})
            await session.commit()
            await state.clear()
            await message.answer(
                "✅ Pause removed. Notifications resumed."
                if lang == "en"
                else "✅ Пауза снята. Уведомления возобновлены."
            )
            return

        match = _DURATION_RE.match(raw)
        if not match:
            await session.commit()
            text = (
                "Invalid format. Examples: <code>30m</code>  <code>2h</code>  <code>1d</code>\n"
                "Or <code>0</code> to remove the pause."
                if lang == "en"
                else "Неверный формат. Примеры: <code>30m</code>  <code>2h</code>  <code>1d</code>\n"
                "Или <code>0</code> для снятия паузы."
            )
            await message.answer(text, reply_markup=build_cancel_keyboard(lang))
            return

        value = int(match.group(1))
        unit = match.group(2).lower()
        if unit == "m":
            delta = timedelta(minutes=value)
        elif unit == "h":
            delta = timedelta(hours=value)
        else:
            delta = timedelta(days=value)
        if delta > timedelta(hours=72):
            delta = timedelta(hours=72)
        paused_until = datetime.now(timezone.utc) + delta
        user.settings = users_repo.merge_user_settings(
            user.settings or {},
            {"paused_until": paused_until.isoformat()},
        )
        await session.commit()

    await state.clear()
    until_str = paused_until.strftime("%H:%M UTC %d %b")
    text = (
        f"✅ Notifications paused until {until_str}.\n"
        "To remove it: “⚙️ Settings” → “⏸ Pause” → enter <code>0</code>"
        if lang == "en"
        else f"✅ Уведомления приостановлены до {until_str}.\n"
        "Чтобы снять паузу — «⚙️ Настройки» → «⏸ Пауза» → введи <code>0</code>"
    )
    await message.answer(text)


@router.callback_query(MenuActionCB.filter(F.action == "digest_toggle"))
async def cb_menu_digest_toggle(
    callback: CallbackQuery,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, callback.from_user.id, settings)
        current = bool((user.settings or {}).get("digest_mode", False))
        lang = preferred_lang(
            user.settings,
            telegram_lang_code=callback.from_user.language_code,
        )
        enable = not current
        user.settings = users_repo.merge_user_settings(
            user.settings or {},
            {"digest_mode": enable},
        )
        await session.commit()
    text = (
        "✅ <b>Digest mode enabled</b>.\nListings will be accumulated and sent once per hour."
        if enable and lang == "en"
        else "✅ Дайджест-режим <b>включён</b>.\nЛистинги будут накапливаться и отправляться раз в час."
        if enable
        else "✅ <b>Digest mode disabled</b>.\nNotifications will arrive instantly again."
        if lang == "en"
        else "✅ Дайджест-режим <b>выключен</b>.\nУведомления снова приходят мгновенно."
    )
    await callback.message.answer(text)
    await callback.answer()
