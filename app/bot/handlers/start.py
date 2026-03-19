from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.callback_data import OBExchangeCB, OBMarketCB, OBModeCB, OBNextCB
from app.bot.keyboards.main_menu import build_main_reply_keyboard
from app.bot.keyboards.onboarding import (
    ALL_EXCHANGES,
    ALL_MARKETS,
    build_step1_keyboard,
    build_step2_keyboard,
    build_step3_keyboard,
    render_done_text,
    render_step1_text,
    render_step2_text,
    render_step3_text,
)
from app.config import Settings
from app.db.models import User
from app.db.repo import analytics as analytics_repo
from app.db.repo import users as users_repo
from app.i18n import get_user_lang, t
from app.services.filtering import normalize_filters

router = Router()


# ─── /start ──────────────────────────────────────────────────────────────────


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if message.from_user is None:
        return

    user_id = message.from_user.id

    async with session_factory() as session:
        existing = await session.get(User, user_id)
        is_new = existing is None
        user = await users_repo.get_or_create_user(session, user_id, settings)
        await analytics_repo.log_event(
            session,
            event_name="session_start",
            source="command",
            user_id=user.id,
            placement="start",
            properties={"command": "start", "is_new": is_new},
        )
        if is_new:
            await analytics_repo.log_event(
                session,
                event_name="user_registered",
                source="command",
                user_id=user.id,
                placement="start",
                properties={"command": "start"},
            )
        await session.commit()
        raw = dict(user.settings or {})

    lang = get_user_lang(raw)

    if not is_new:
        # Returning user — brief welcome back with current settings summary
        filters = normalize_filters(raw, settings)
        exchanges_str = ", ".join(
            e.capitalize() for e in ALL_EXCHANGES if e in filters.enabled_exchanges
        ) or "—"
        markets_str = " + ".join(
            m.capitalize() for m in ALL_MARKETS if m in filters.enabled_market_types
        ) or "—"
        mode_str = t("start.mode_digest", lang) if raw.get("digest_mode") else t("start.mode_instant", lang)
        await message.answer(
            t("start.welcome_back", lang,
              exchanges=exchanges_str,
              markets=markets_str,
              usdt=t("start.yes", lang) if filters.only_usdt else t("start.no", lang),
              score=filters.min_score,
              mode=mode_str),
            reply_markup=build_main_reply_keyboard(lang),
        )
        return

    # New user — onboarding wizard
    filters = normalize_filters(raw, settings)
    await message.answer(t("start.welcome_new", lang))
    await message.answer(
        render_step1_text(lang),
        reply_markup=build_step1_keyboard(filters.enabled_exchanges, lang),
    )


# ─── Onboarding callbacks ─────────────────────────────────────────────────────


@router.callback_query(OBExchangeCB.filter())
async def cb_ob_exchange(
    query: CallbackQuery,
    callback_data: OBExchangeCB,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if query.from_user is None or query.message is None:
        await query.answer()
        return

    exchange = callback_data.exchange
    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, query.from_user.id, settings)
        raw = dict(user.settings or users_repo.build_default_settings(settings))
        exchanges: set[str] = {
            str(x).lower()
            for x in raw.get("enabled_exchanges", settings.default_enabled_exchanges)
        }
        _lang = get_user_lang(user.settings)
        if exchange in exchanges:
            if len(exchanges) <= 1:
                await query.answer(t("start.need_exchange", _lang), show_alert=True)
                return
            exchanges.discard(exchange)
        else:
            exchanges.add(exchange)
        raw["enabled_exchanges"] = sorted(exchanges)
        user.settings = raw
        await session.commit()
        filters = normalize_filters(raw, settings)

    lang = get_user_lang(raw)
    await query.message.edit_text(  # type: ignore[union-attr]
        render_step1_text(lang),
        reply_markup=build_step1_keyboard(filters.enabled_exchanges, lang),
    )
    await query.answer()


@router.callback_query(OBMarketCB.filter())
async def cb_ob_market(
    query: CallbackQuery,
    callback_data: OBMarketCB,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if query.from_user is None or query.message is None:
        await query.answer()
        return

    market = callback_data.market
    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, query.from_user.id, settings)
        raw = dict(user.settings or users_repo.build_default_settings(settings))
        markets: set[str] = {
            str(x).lower()
            for x in raw.get("enabled_market_types", settings.default_enabled_market_types)
        }
        _lang = get_user_lang(user.settings)
        if market in markets:
            if len(markets) <= 1:
                await query.answer(t("start.need_market", _lang), show_alert=True)
                return
            markets.discard(market)
        else:
            markets.add(market)
        raw["enabled_market_types"] = sorted(markets)
        user.settings = raw
        await session.commit()
        filters = normalize_filters(raw, settings)

    lang = get_user_lang(raw)
    await query.message.edit_text(  # type: ignore[union-attr]
        render_step2_text(lang),
        reply_markup=build_step2_keyboard(filters.enabled_market_types, lang),
    )
    await query.answer()


@router.callback_query(OBNextCB.filter())
async def cb_ob_next(
    query: CallbackQuery,
    callback_data: OBNextCB,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if query.from_user is None or query.message is None:
        await query.answer()
        return

    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, query.from_user.id, settings)
        raw = dict(user.settings or users_repo.build_default_settings(settings))
        await session.commit()
    filters = normalize_filters(raw, settings)
    lang = get_user_lang(raw)

    if callback_data.from_step == 1:
        await query.message.edit_text(  # type: ignore[union-attr]
            render_step2_text(lang),
            reply_markup=build_step2_keyboard(filters.enabled_market_types, lang),
        )
    elif callback_data.from_step == 2:
        await query.message.edit_text(  # type: ignore[union-attr]
            render_step3_text(lang),
            reply_markup=build_step3_keyboard(lang),
        )
    await query.answer()


@router.callback_query(OBModeCB.filter())
async def cb_ob_mode(
    query: CallbackQuery,
    callback_data: OBModeCB,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if query.from_user is None or query.message is None:
        await query.answer()
        return

    digest_mode = bool(callback_data.digest)
    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, query.from_user.id, settings)
        raw = dict(user.settings or users_repo.build_default_settings(settings))
        raw["digest_mode"] = digest_mode
        user.settings = raw
        await session.commit()
        filters = normalize_filters(raw, settings)

    lang = get_user_lang(raw)
    # Edit to completion screen — no keyboard (wizard is done)
    await query.message.edit_text(  # type: ignore[union-attr]
        render_done_text(filters, digest_mode, lang),
    )
    # Show the main reply keyboard so the user can navigate without commands
    await query.message.answer(  # type: ignore[union-attr]
        t("start.menu_hint", lang),
        reply_markup=build_main_reply_keyboard(lang),
    )
    await query.answer(t("start.settings_saved", lang))
