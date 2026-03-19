from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Event, User
from app.db.repo import digest as digest_repo
from app.i18n import get_user_lang, t

LOGGER = logging.getLogger(__name__)

_MAX_EVENTS_IN_DIGEST = 20


class DigestService:
    def __init__(self, bot: Bot, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._bot = bot
        self._session_factory = session_factory

    async def send_pending_digests(self) -> None:
        """Called by scheduler: collect queued events per user and send summaries."""
        async with self._session_factory() as session:
            user_ids = await digest_repo.list_users_with_queue(session)
        for user_id in user_ids:
            async with self._session_factory() as session:
                user_obj = await session.get(User, user_id)
                lang = get_user_lang(user_obj.settings if user_obj else None)
                queue_items = await digest_repo.list_user_queue_items(session, user_id)

            if not queue_items:
                continue

            event_ids = [event_id for event_id, _ in queue_items]
            events = [event for _, event in queue_items]
            text = _format_digest(events, lang=lang)
            delivered = await self._send(user_id, text)

            if delivered:
                async with self._session_factory() as session:
                    await digest_repo.delete_user_queue_items(session, user_id, event_ids)
                    await session.commit()

    async def _send(self, user_id: int, text: str) -> bool:
        try:
            await self._bot.send_message(chat_id=user_id, text=text)
            return True
        except TelegramRetryAfter as e:
            LOGGER.warning("Flood control for digest to %s, retrying after %ss", user_id, e.retry_after)
            await asyncio.sleep(e.retry_after)
            try:
                await self._bot.send_message(chat_id=user_id, text=text)
                return True
            except Exception:
                LOGGER.exception("Retry failed for digest to user %s", user_id)
                return False
        except TelegramForbiddenError:
            LOGGER.warning("User %s blocked bot, skipping digest", user_id)
            return False
        except TelegramBadRequest:
            LOGGER.exception("Bad request sending digest to user %s", user_id)
            return False
        except Exception:
            LOGGER.exception("Unexpected error sending digest to user %s", user_id)
            return False


def is_digest_mode(settings: dict) -> bool:
    return bool(settings.get("digest_mode", False))


def _format_digest(events: list[Event], lang: str = "ru") -> str:
    shown = events[:_MAX_EVENTS_IN_DIGEST]
    overflow = len(events) - len(shown)

    lines = [t("digest.header", lang, count=len(events))]
    for ev in shown:
        ts = ev.first_seen_at.strftime("%H:%M")
        market = (
            t("digest.market_spot", lang)
            if ev.market_type.value == "spot"
            else t("digest.market_fut", lang)
        )
        lines.append(
            f"• <b>{ev.symbol_base}/{ev.symbol_quote}</b> "
            f"{ev.exchange.capitalize()} {market} "
            f"| Score {ev.score} | {ts} UTC"
        )
    if overflow > 0:
        lines.append(t("digest.overflow", lang, count=overflow))
    return "\n".join(lines)
