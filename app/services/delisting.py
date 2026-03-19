from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.repo import deliveries as deliveries_repo
from app.db.repo import watchlist as watchlist_repo
from app.i18n import get_user_lang, t
from app.services.detector import DelistingAlert

LOGGER = logging.getLogger(__name__)


class DelistingNotifier:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def notify(self, session: AsyncSession, alerts: list[DelistingAlert]) -> None:
        if not alerts:
            return

        bases = [a.symbol_base.upper() for a in alerts]
        watchers = await watchlist_repo.find_users_watching(session, bases)
        # Also notify users who previously received a listing notification for the coin
        delivery_users = await deliveries_repo.find_users_notified_for_bases(session, bases)

        # Collect all relevant alerts per user (batching)
        user_alerts: dict[int, list[DelistingAlert]] = {}
        for alert in alerts:
            base = alert.symbol_base.upper()
            user_ids: set[int] = set(watchers.get(base, []))
            user_ids.update(delivery_users.get(base, []))
            for user_id in user_ids:
                user_alerts.setdefault(user_id, []).append(alert)

        # Send one batched message per user
        for user_id, user_alert_list in user_alerts.items():
            user_obj = await session.get(User, user_id)
            lang = get_user_lang(user_obj.settings if user_obj else None)
            text = _format_delisting_batch(user_alert_list, lang=lang)
            await self._send(user_id, text)

    async def _send(self, user_id: int, text: str) -> None:
        try:
            await self._bot.send_message(chat_id=user_id, text=text)
        except TelegramRetryAfter as e:
            LOGGER.warning("Flood control for delisting alert to %s, retrying after %ss", user_id, e.retry_after)
            await asyncio.sleep(e.retry_after)
            try:
                await self._bot.send_message(chat_id=user_id, text=text)
            except Exception:
                LOGGER.exception("Retry failed for delisting alert to user %s", user_id)
        except TelegramForbiddenError:
            LOGGER.warning("User %s blocked bot, skipping delisting alert", user_id)
        except TelegramBadRequest:
            LOGGER.exception("Bad request sending delisting alert to user %s", user_id)


def _format_delisting_batch(alerts: list[DelistingAlert], lang: str = "ru") -> str:
    """Format one or many delisting alerts into a single message."""
    if len(alerts) == 1:
        return _format_delisting_message(alerts[0], lang)

    header = t("delisting.batch_header", lang, count=len(alerts))
    lines = [header]
    for alert in alerts[:20]:  # cap display at 20 rows
        market = (
            t("delisting.market_spot", lang)
            if alert.market_type.value == "spot"
            else t("delisting.market_futures", lang)
        )
        lines.append(
            f"• <b>{alert.symbol_base}/{alert.symbol_quote}</b>"
            f" — {alert.exchange.capitalize()} {market}"
        )
    if len(alerts) > 20:
        lines.append(t("delisting.batch_overflow", lang, count=len(alerts) - 20))
    lines.append(t("delisting.batch_footer", lang))
    return "\n".join(lines)


def _format_delisting_message(alert: DelistingAlert, lang: str = "ru") -> str:
    market = (
        t("delisting.market_spot", lang)
        if alert.market_type.value == "spot"
        else t("delisting.market_futures", lang)
    )
    return t(
        "delisting.message", lang,
        base=alert.symbol_base,
        quote=alert.symbol_quote,
        exchange=alert.exchange.capitalize(),
        market=market,
    )
