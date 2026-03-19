from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callback_data import (
    FilterCloseCB,
    FilterExchangeCB,
    FilterMarketCB,
    FilterOnlyUsdtCB,
    FilterScoreCB,
)
from app.services.filtering import UserFilters

# Canonical order for display; matches scoring weight order.
ALL_EXCHANGES = ["binance", "bybit", "okx", "mexc", "coinbase"]
ALL_MARKETS = ["spot", "futures"]

_MIN_SCORE = 0
_MAX_SCORE = 100


def _label(key: str, lang: str, **kwargs: int | str) -> str:
    ru = {
        "yes": "да",
        "no": "нет",
        "summary": (
            "⚙️ <b>Настройки уведомлений</b>\n\n"
            "Биржи: <b>{active_count}/{total_count}</b> активных\n"
            "Рынки: <b>{markets}</b>\n"
            "Только USDT: <b>{only_usdt}</b>\n"
            "Мин. скор: <b>{min_score}/100</b>\n\n"
            "<i>Нажми кнопку чтобы изменить настройку</i>"
        ),
        "only_usdt.button": "Только USDT: {icon}",
        "score.button": "Мин. скор: {score}",
        "close": "❌ Закрыть",
    }
    en = {
        "yes": "yes",
        "no": "no",
        "summary": (
            "⚙️ <b>Notification filters</b>\n\n"
            "Exchanges: <b>{active_count}/{total_count}</b> enabled\n"
            "Markets: <b>{markets}</b>\n"
            "USDT only: <b>{only_usdt}</b>\n"
            "Min score: <b>{min_score}/100</b>\n\n"
            "<i>Tap a button to change the setting</i>"
        ),
        "only_usdt.button": "USDT only: {icon}",
        "score.button": "Min score: {score}",
        "close": "❌ Close",
    }
    text = (en if lang == "en" else ru)[key]
    return text.format(**kwargs) if kwargs else text


def render_filters_text(filters: UserFilters, lang: str = "ru") -> str:
    active_count = sum(1 for exchange in ALL_EXCHANGES if exchange in filters.enabled_exchanges)
    total_count = len(ALL_EXCHANGES)

    markets_str = " + ".join(
        market.capitalize()
        for market in ALL_MARKETS
        if market in filters.enabled_market_types
    ) or "—"
    usdt_str = _label("yes", lang) if filters.only_usdt else _label("no", lang)

    return _label(
        "summary",
        lang,
        active_count=active_count,
        total_count=total_count,
        markets=markets_str,
        only_usdt=usdt_str,
        min_score=filters.min_score,
    )


def build_filters_keyboard(
    filters: UserFilters,
    lang: str = "ru",
) -> InlineKeyboardMarkup:
    def exch_btn(exchange: str) -> InlineKeyboardButton:
        active = exchange in filters.enabled_exchanges
        label = f"{'✅' if active else '❌'} {exchange.capitalize()}"
        return InlineKeyboardButton(
            text=label,
            callback_data=FilterExchangeCB(exchange=exchange).pack(),
        )

    def market_btn(market: str) -> InlineKeyboardButton:
        active = market in filters.enabled_market_types
        label = f"{'✅' if active else '❌'} {market.capitalize()}"
        return InlineKeyboardButton(
            text=label,
            callback_data=FilterMarketCB(market=market).pack(),
        )

    usdt_icon = "✅" if filters.only_usdt else "❌"
    score = filters.min_score
    can_decrease = score > _MIN_SCORE
    can_increase = score < _MAX_SCORE

    rows = [
        [exch_btn(exchange) for exchange in ALL_EXCHANGES[:3]],
        [exch_btn(exchange) for exchange in ALL_EXCHANGES[3:]],
        [market_btn(market) for market in ALL_MARKETS],
        [
            InlineKeyboardButton(
                text=_label("only_usdt.button", lang, icon=usdt_icon),
                callback_data=FilterOnlyUsdtCB().pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text=_label("score.button", lang, score=score),
                callback_data=FilterScoreCB(delta=0).pack(),
            ),
            InlineKeyboardButton(
                text="−10" if can_decrease else "·",
                callback_data=FilterScoreCB(delta=-10).pack(),
            ),
            InlineKeyboardButton(
                text="+10" if can_increase else "·",
                callback_data=FilterScoreCB(delta=10).pack(),
            ),
        ],
        [
            InlineKeyboardButton(
                text=_label("close", lang),
                callback_data=FilterCloseCB().pack(),
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
