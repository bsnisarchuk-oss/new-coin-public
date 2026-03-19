from __future__ import annotations

from typing import Any

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot.callback_data import (
    FilterCloseCB,
    FilterExchangeCB,
    FilterMarketCB,
    FilterOnlyUsdtCB,
    FilterScoreCB,
)
from app.bot.keyboards.filters_menu import (
    _MAX_SCORE,
    _MIN_SCORE,
    build_filters_keyboard,
    render_filters_text,
)
from app.bot.lang import preferred_lang
from app.config import Settings
from app.db.repo import users as users_repo
from app.services.filtering import normalize_filters

router = Router()

_SCORE_STEP = 10


def _as_switch(value: str) -> bool:
    return value.strip().lower() in {"on", "1", "true", "yes", "y"}


def _text(key: str, lang: str, **kwargs: str | int) -> str:
    ru = {
        "invalid_score": "Неверное значение скора. Используй /help",
        "invalid_format": "Неверный формат. Используй /help",
        "need_exchange": "Нужна хотя бы одна биржа",
        "need_market": "Нужен хотя бы один тип рынка",
        "score_hint": (
            "Мин. скор фильтрует листинги по качеству.\n"
            "0 = все листинги, 50 = средние и выше, 100 = только лучшие."
        ),
        "score_boundary.min": "Уже минимум ({score})",
        "score_boundary.max": "Уже максимум ({score})",
    }
    en = {
        "invalid_score": "Invalid score value. Use /help",
        "invalid_format": "Invalid format. Use /help",
        "need_exchange": "At least one exchange is required",
        "need_market": "At least one market type is required",
        "score_hint": (
            "Min score filters listings by quality.\n"
            "0 = all listings, 50 = average and above, 100 = only the best."
        ),
        "score_boundary.min": "Already at minimum ({score})",
        "score_boundary.max": "Already at maximum ({score})",
    }
    text = (en if lang == "en" else ru)[key]
    return text.format(**kwargs) if kwargs else text


async def _load_user_and_lang(
    user_id: int,
    telegram_lang_code: str | None,
    session_factory: async_sessionmaker,
    settings: Settings,
):
    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, user_id, settings)
        lang = preferred_lang(
            user.settings,
            telegram_lang_code=telegram_lang_code,
        )
        return session, user, lang


@router.message(Command("filters"))
async def cmd_filters(
    message: Message,
    command: CommandObject,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return

    user_id = message.from_user.id
    args = (command.args or "").split()

    if not args:
        async with session_factory() as session:
            user = await users_repo.get_or_create_user(session, user_id, settings)
            raw = dict(user.settings or users_repo.build_default_settings(settings))
            lang = preferred_lang(
                user.settings,
                telegram_lang_code=message.from_user.language_code,
            )
            await session.commit()
        filters = normalize_filters(raw, settings)
        await message.answer(
            render_filters_text(filters, lang),
            reply_markup=build_filters_keyboard(filters, lang),
        )
        return

    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, user_id, settings)
        current = dict(user.settings or users_repo.build_default_settings(settings))
        lang = preferred_lang(
            user.settings,
            telegram_lang_code=message.from_user.language_code,
        )
        patch: dict[str, Any] = {}
        action = args[0].lower()

        if action == "only_usdt" and len(args) >= 2:
            patch["only_usdt"] = _as_switch(args[1])
        elif action == "min_score" and len(args) >= 2:
            try:
                patch["min_score"] = max(_MIN_SCORE, min(_MAX_SCORE, int(args[1])))
            except ValueError:
                await session.commit()
                await message.answer(_text("invalid_score", lang))
                return
        elif action == "exchange" and len(args) >= 3:
            exchange = args[1].strip().lower()
            state = _as_switch(args[2])
            exchanges = {
                str(item).lower()
                for item in current.get("enabled_exchanges", settings.default_enabled_exchanges)
            }
            if state:
                exchanges.add(exchange)
            else:
                exchanges.discard(exchange)
            patch["enabled_exchanges"] = sorted(exchanges)
        elif action == "market" and len(args) >= 3:
            market = args[1].strip().lower()
            state = _as_switch(args[2])
            markets = {
                str(item).lower()
                for item in current.get(
                    "enabled_market_types",
                    settings.default_enabled_market_types,
                )
            }
            if state:
                markets.add(market)
            else:
                markets.discard(market)
            patch["enabled_market_types"] = sorted(markets)
        else:
            await session.commit()
            await message.answer(_text("invalid_format", lang))
            return

        user.settings = users_repo.merge_user_settings(current, patch)
        await session.commit()
        filters = normalize_filters(user.settings, settings)

    await message.answer(
        render_filters_text(filters, lang),
        reply_markup=build_filters_keyboard(filters, lang),
    )


@router.callback_query(FilterExchangeCB.filter())
async def cb_filter_exchange(
    query: CallbackQuery,
    callback_data: FilterExchangeCB,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if query.from_user is None or query.message is None:
        await query.answer()
        return

    exchange = callback_data.exchange
    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, query.from_user.id, settings)
        lang = preferred_lang(
            user.settings,
            telegram_lang_code=query.from_user.language_code,
        )
        raw = dict(user.settings or users_repo.build_default_settings(settings))
        exchanges: set[str] = {
            str(item).lower()
            for item in raw.get("enabled_exchanges", settings.default_enabled_exchanges)
        }
        if exchange in exchanges:
            if len(exchanges) <= 1:
                await query.answer(_text("need_exchange", lang), show_alert=True)
                return
            exchanges.discard(exchange)
        else:
            exchanges.add(exchange)
        raw["enabled_exchanges"] = sorted(exchanges)
        user.settings = raw
        await session.commit()
        filters = normalize_filters(raw, settings)

    await query.message.edit_text(
        render_filters_text(filters, lang),
        reply_markup=build_filters_keyboard(filters, lang),
    )
    await query.answer()


@router.callback_query(FilterMarketCB.filter())
async def cb_filter_market(
    query: CallbackQuery,
    callback_data: FilterMarketCB,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if query.from_user is None or query.message is None:
        await query.answer()
        return

    market = callback_data.market
    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, query.from_user.id, settings)
        lang = preferred_lang(
            user.settings,
            telegram_lang_code=query.from_user.language_code,
        )
        raw = dict(user.settings or users_repo.build_default_settings(settings))
        markets: set[str] = {
            str(item).lower()
            for item in raw.get("enabled_market_types", settings.default_enabled_market_types)
        }
        if market in markets:
            if len(markets) <= 1:
                await query.answer(_text("need_market", lang), show_alert=True)
                return
            markets.discard(market)
        else:
            markets.add(market)
        raw["enabled_market_types"] = sorted(markets)
        user.settings = raw
        await session.commit()
        filters = normalize_filters(raw, settings)

    await query.message.edit_text(
        render_filters_text(filters, lang),
        reply_markup=build_filters_keyboard(filters, lang),
    )
    await query.answer()


@router.callback_query(FilterOnlyUsdtCB.filter())
async def cb_filter_only_usdt(
    query: CallbackQuery,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if query.from_user is None or query.message is None:
        await query.answer()
        return

    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, query.from_user.id, settings)
        lang = preferred_lang(
            user.settings,
            telegram_lang_code=query.from_user.language_code,
        )
        raw = dict(user.settings or users_repo.build_default_settings(settings))
        raw["only_usdt"] = not bool(raw.get("only_usdt", settings.default_only_usdt))
        user.settings = raw
        await session.commit()
        filters = normalize_filters(raw, settings)

    await query.message.edit_text(
        render_filters_text(filters, lang),
        reply_markup=build_filters_keyboard(filters, lang),
    )
    await query.answer()


@router.callback_query(FilterScoreCB.filter())
async def cb_filter_score(
    query: CallbackQuery,
    callback_data: FilterScoreCB,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if query.from_user is None or query.message is None:
        await query.answer()
        return

    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, query.from_user.id, settings)
        lang = preferred_lang(
            user.settings,
            telegram_lang_code=query.from_user.language_code,
        )

        if callback_data.delta == 0:
            await query.answer(_text("score_hint", lang), show_alert=True)
            await session.commit()
            return

        raw = dict(user.settings or users_repo.build_default_settings(settings))
        current_score = int(raw.get("min_score", settings.default_min_score))
        new_score = max(_MIN_SCORE, min(_MAX_SCORE, current_score + callback_data.delta))

        if new_score == current_score:
            boundary_key = (
                "score_boundary.min"
                if callback_data.delta < 0
                else "score_boundary.max"
            )
            await query.answer(_text(boundary_key, lang, score=current_score))
            await session.commit()
            return

        raw["min_score"] = new_score
        user.settings = raw
        await session.commit()
        filters = normalize_filters(raw, settings)

    await query.message.edit_text(
        render_filters_text(filters, lang),
        reply_markup=build_filters_keyboard(filters, lang),
    )
    await query.answer()


@router.callback_query(FilterCloseCB.filter())
async def cb_filter_close(query: CallbackQuery) -> None:
    if query.message is not None:
        await query.message.delete()
    await query.answer()
