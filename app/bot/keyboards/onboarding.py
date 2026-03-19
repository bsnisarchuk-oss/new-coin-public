from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callback_data import OBExchangeCB, OBMarketCB, OBModeCB, OBNextCB
from app.i18n import t
from app.services.filtering import UserFilters

ALL_EXCHANGES = ["binance", "bybit", "okx", "mexc", "coinbase"]
ALL_MARKETS = ["spot", "futures"]


# ─── Step 1: Exchanges ───────────────────────────────────────────────────────


def render_step1_text(lang: str = "ru") -> str:
    return t("onboarding.step1.text", lang)


def build_step1_keyboard(selected: set[str], lang: str = "ru") -> InlineKeyboardMarkup:
    def btn(exchange: str) -> InlineKeyboardButton:
        icon = "✅" if exchange in selected else "❌"
        return InlineKeyboardButton(
            text=f"{icon} {exchange.capitalize()}",
            callback_data=OBExchangeCB(exchange=exchange).pack(),
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [btn(e) for e in ALL_EXCHANGES[:3]],
            [btn(e) for e in ALL_EXCHANGES[3:]],
            [
                InlineKeyboardButton(
                    text=t("onboarding.continue", lang),
                    callback_data=OBNextCB(from_step=1).pack(),
                )
            ],
        ]
    )


# ─── Step 2: Market types ────────────────────────────────────────────────────


def render_step2_text(lang: str = "ru") -> str:
    return t("onboarding.step2.text", lang)


def build_step2_keyboard(selected: set[str], lang: str = "ru") -> InlineKeyboardMarkup:
    def btn(market: str) -> InlineKeyboardButton:
        icon = "✅" if market in selected else "❌"
        return InlineKeyboardButton(
            text=f"{icon} {market.capitalize()}",
            callback_data=OBMarketCB(market=market).pack(),
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [btn(m) for m in ALL_MARKETS],
            [
                InlineKeyboardButton(
                    text=t("onboarding.continue", lang),
                    callback_data=OBNextCB(from_step=2).pack(),
                )
            ],
        ]
    )


# ─── Step 3: Notification mode ───────────────────────────────────────────────


def render_step3_text(lang: str = "ru") -> str:
    return t("onboarding.step3.text", lang)


def build_step3_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("onboarding.mode.instant", lang),
                    callback_data=OBModeCB(digest=0).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("onboarding.mode.digest", lang),
                    callback_data=OBModeCB(digest=1).pack(),
                )
            ],
        ]
    )


# ─── Done ────────────────────────────────────────────────────────────────────


def render_done_text(filters: UserFilters, digest_mode: bool, lang: str = "ru") -> str:
    exchanges_str = ", ".join(e.capitalize() for e in ALL_EXCHANGES if e in filters.enabled_exchanges)
    markets_str = " + ".join(m.capitalize() for m in ALL_MARKETS if m in filters.enabled_market_types)
    mode_str = t("onboarding.done.mode.digest", lang) if digest_mode else t("onboarding.done.mode.instant", lang)

    return t(
        "onboarding.done.text",
        lang,
        exchanges=exchanges_str,
        markets=markets_str,
        mode=mode_str,
    )
