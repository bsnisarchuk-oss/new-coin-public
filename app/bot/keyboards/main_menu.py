from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from app.bot.callback_data import MenuActionCB
from app.i18n import t


def build_main_reply_keyboard(lang: str = "ru") -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text=t("menu.main.watch", lang)),
        KeyboardButton(text=t("menu.main.alerts", lang)),
    )
    builder.row(
        KeyboardButton(text=t("menu.main.settings", lang)),
        KeyboardButton(text=t("menu.main.analytics", lang)),
    )
    builder.row(
        KeyboardButton(text=t("menu.main.help", lang)),
    )
    return builder.as_markup(resize_keyboard=True)


def build_watch_section(lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("menu.watch.list", lang), callback_data=MenuActionCB(action="watchlist"))
    builder.button(text=t("menu.watch.add", lang), callback_data=MenuActionCB(action="watch_add"))
    builder.button(text=t("menu.watch.remove", lang), callback_data=MenuActionCB(action="watch_remove"))
    builder.button(text=t("menu.common.close", lang), callback_data=MenuActionCB(action="close"))
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def build_alerts_section(lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("menu.alerts.list", lang), callback_data=MenuActionCB(action="alerts_list"))
    builder.button(text=t("menu.alerts.add", lang), callback_data=MenuActionCB(action="alert_add"))
    builder.button(text=t("menu.alerts.remove", lang), callback_data=MenuActionCB(action="unalert"))
    builder.button(text=t("menu.common.close", lang), callback_data=MenuActionCB(action="close"))
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def build_settings_section(lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("menu.settings.filters", lang), callback_data=MenuActionCB(action="filters"))
    builder.button(text=t("menu.settings.presets", lang), callback_data=MenuActionCB(action="presets"))
    builder.button(text=t("menu.settings.pause", lang), callback_data=MenuActionCB(action="pause"))
    builder.button(text=t("menu.settings.digest", lang), callback_data=MenuActionCB(action="digest_toggle"))
    builder.button(text=t("menu.common.close", lang), callback_data=MenuActionCB(action="close"))
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def build_analytics_section(lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("menu.analytics.stats", lang), callback_data=MenuActionCB(action="analytics"))
    builder.button(text=t("menu.analytics.top", lang), callback_data=MenuActionCB(action="top"))
    builder.button(text=t("menu.analytics.history", lang), callback_data=MenuActionCB(action="history"))
    builder.button(text=t("menu.analytics.export", lang), callback_data=MenuActionCB(action="export"))
    builder.button(text=t("menu.common.close", lang), callback_data=MenuActionCB(action="close"))
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def build_help_section(lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("menu.help.help", lang), callback_data=MenuActionCB(action="help"))
    builder.button(text=t("menu.help.status", lang), callback_data=MenuActionCB(action="status"))
    builder.button(text=t("menu.common.close", lang), callback_data=MenuActionCB(action="close"))
    builder.adjust(2, 1)
    return builder.as_markup()


def build_cancel_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("menu.common.cancel", lang), callback_data=MenuActionCB(action="cancel_fsm"))
    return builder.as_markup()
