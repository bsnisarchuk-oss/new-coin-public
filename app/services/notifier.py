from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.event_actions import build_event_actions
from app.config import Settings
from app.db.models import Event, MuteRule, User
from app.db.repo import analytics as analytics_repo
from app.db.repo import deliveries as deliveries_repo
from app.db.repo import digest as digest_repo
from app.db.repo import mutes as mutes_repo
from app.db.repo import users as users_repo
from app.i18n import get_user_lang, t
from app.metrics import notifications_sent
from app.services.arbitrage import ArbitrageService
from app.services.coingecko import CoinInfoService
from app.services.dedup import DedupDecision, DedupService
from app.services.enrich import EnrichmentService
from app.services.filtering import UserFilters, event_passes_filters, normalize_filters
from app.services.formatter import extract_symbol, format_event_message
from app.services.scoring import calculate_score

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class _UserDeliveryContext:
    user: User
    filters: UserFilters
    mute_rules: list[MuteRule]
    lang: str
    manual_digest_mode: bool
    linked_channel_id: int | str | None


class EventNotifier:
    def __init__(
        self,
        bot: Bot,
        settings: Settings,
        enrichment_service: EnrichmentService,
        dedup_service: DedupService,
        arbitrage_service: ArbitrageService | None = None,
        coin_info_service: CoinInfoService | None = None,
    ) -> None:
        self._bot = bot
        self._settings = settings
        self._enrichment = enrichment_service
        self._dedup = dedup_service
        self._arbitrage = arbitrage_service
        self._coin_info = coin_info_service
        self._enrich_concurrency = 10

    async def _enrich_one(self, event: Event) -> None:
        symbol = extract_symbol(event)
        enriched, flags = await self._enrichment.enrich_event(
            exchange=event.exchange,
            market_type=event.market_type.value,
            symbol=symbol,
            base=event.symbol_base,
            quote=event.symbol_quote,
        )
        if self._arbitrage is not None:
            arb = await self._arbitrage.fetch_all_prices(
                base=event.symbol_base,
                quote=event.symbol_quote,
            )
            if arb.prices:
                enriched["arb_prices"] = arb.prices
            if arb.spread_pct is not None:
                enriched["arb_spread_pct"] = round(arb.spread_pct, 4)
            if arb.cheapest:
                enriched["arb_cheapest"] = arb.cheapest
            if arb.most_expensive:
                enriched["arb_most_expensive"] = arb.most_expensive

        if self._coin_info is not None:
            try:
                coin_info = await self._coin_info.get_coin_info(event.symbol_base)
                if coin_info:
                    enriched["coin_info"] = coin_info
            except Exception:
                LOGGER.debug("CoinGecko info fetch failed for %s", event.symbol_base)

        event.enriched = enriched
        event.flags = flags
        event.score = calculate_score(event.exchange, event.symbol_quote, flags, enriched)

    async def _enrich_events(self, events: list[Event]) -> None:
        semaphore = asyncio.Semaphore(self._enrich_concurrency)

        async def _bounded(event: Event) -> None:
            async with semaphore:
                await self._enrich_one(event)

        await asyncio.gather(*(_bounded(event) for event in events))

    def _build_user_contexts(
        self,
        users: list[User],
        mutes_by_user: dict[int, list[MuteRule]],
    ) -> list[_UserDeliveryContext]:
        contexts: list[_UserDeliveryContext] = []
        for user in users:
            settings = user.settings or {}
            contexts.append(
                _UserDeliveryContext(
                    user=user,
                    filters=normalize_filters(settings, self._settings),
                    mute_rules=mutes_by_user.get(user.id, []),
                    lang=get_user_lang(settings),
                    manual_digest_mode=bool(settings.get("digest_mode", False)),
                    linked_channel_id=settings.get("linked_channel_id"),
                )
            )
        return contexts

    async def _send_listing_message(
        self,
        *,
        user_id: int,
        msg_text: str,
        reply_markup: Any,
    ) -> bool:
        try:
            await self._bot.send_message(
                chat_id=user_id,
                text=msg_text,
                reply_markup=reply_markup,
            )
            return True
        except TelegramRetryAfter as exc:
            LOGGER.warning(
                "Flood control hit for user %s, retrying after %ss",
                user_id,
                exc.retry_after,
            )
            await asyncio.sleep(exc.retry_after)
            try:
                await self._bot.send_message(
                    chat_id=user_id,
                    text=msg_text,
                    reply_markup=reply_markup,
                )
                return True
            except Exception:
                LOGGER.exception("Retry after flood control failed for user %s", user_id)
                return False
        except TelegramForbiddenError:
            LOGGER.warning("User %s blocked bot, skipping delivery", user_id)
            return False
        except TelegramBadRequest:
            LOGGER.exception("Telegram bad request for user %s", user_id)
            return False

    async def process_events(self, session: AsyncSession, events: list[Event]) -> None:
        users = await users_repo.list_all_users(session)
        if not users:
            LOGGER.info("No users in database, skipping notifications")
            return

        await self._enrich_events(events)

        user_ids = [user.id for user in users]
        mutes_by_user = await mutes_repo.list_mutes_for_users(session, user_ids)
        user_contexts = self._build_user_contexts(users, mutes_by_user)
        digest_switch_notified: set[int] = set()
        message_cache: dict[tuple[str, str], str] = {}
        keyboard_cache: dict[tuple[str, str], Any] = {}

        for event in events:
            for user_ctx in user_contexts:
                if not event_passes_filters(event, user_ctx.filters, user_ctx.mute_rules):
                    continue

                decision = await self._dedup.check_delivery(
                    session,
                    user_ctx.user,
                    event.event_key,
                )
                if decision in {
                    DedupDecision.SKIP_ALREADY_SENT,
                    DedupDecision.SKIP_PAUSED,
                }:
                    continue

                queue_digest = user_ctx.manual_digest_mode or decision in {
                    DedupDecision.QUEUE_DIGEST_ACTIVE,
                    DedupDecision.QUEUE_RATE_LIMITED,
                }

                if queue_digest:
                    if (
                        decision == DedupDecision.QUEUE_RATE_LIMITED
                        and not user_ctx.manual_digest_mode
                        and user_ctx.user.id not in digest_switch_notified
                    ):
                        digest_switch_notified.add(user_ctx.user.id)
                        try:
                            await self._bot.send_message(
                                chat_id=user_ctx.user.id,
                                text=t("notifier.auto_digest", user_ctx.lang),
                            )
                        except Exception:
                            LOGGER.warning(
                                "Failed to notify user %s about auto-digest switch",
                                user_ctx.user.id,
                            )

                    await digest_repo.enqueue(session, user_ctx.user.id, event.id)
                    await deliveries_repo.create_delivery(
                        session=session,
                        user_id=user_ctx.user.id,
                        event_id=event.id,
                        event_key=event.event_key,
                    )
                    await _log_delivery(
                        session,
                        user_ctx.user.id,
                        event,
                        "notification_queued",
                        "digest",
                    )
                    notifications_sent.labels(delivery_mode="digest").inc()
                    continue

                if decision != DedupDecision.ALLOW:
                    continue

                cache_key = (event.event_key, user_ctx.lang)
                msg_text = message_cache.get(cache_key)
                if msg_text is None:
                    try:
                        msg_text = format_event_message(event, lang=user_ctx.lang)
                    except Exception:
                        LOGGER.exception(
                            "Failed to format event message for event %s",
                            event.event_key,
                        )
                        continue
                    message_cache[cache_key] = msg_text
                reply_markup = keyboard_cache.get(cache_key)
                if reply_markup is None:
                    reply_markup = build_event_actions(event, user_ctx.lang)
                    keyboard_cache[cache_key] = reply_markup

                delivered = await self._send_listing_message(
                    user_id=user_ctx.user.id,
                    msg_text=msg_text,
                    reply_markup=reply_markup,
                )
                if not delivered:
                    continue

                # Message was sent. Record delivery and analytics separately so DB
                # errors do not bubble up and roll back the whole cycle.
                try:
                    await deliveries_repo.create_delivery(
                        session=session,
                        user_id=user_ctx.user.id,
                        event_id=event.id,
                        event_key=event.event_key,
                    )
                    await _log_delivery(
                        session,
                        user_ctx.user.id,
                        event,
                        "notification_impression",
                        "instant",
                    )
                    notifications_sent.labels(delivery_mode="instant").inc()
                except Exception:
                    LOGGER.exception(
                        "Failed to record delivery for user %s event %s",
                        user_ctx.user.id,
                        event.event_key,
                    )

                if user_ctx.linked_channel_id:
                    try:
                        await self._bot.send_message(
                            chat_id=user_ctx.linked_channel_id,
                            text=msg_text,
                        )
                    except Exception:
                        LOGGER.warning(
                            "Failed to forward event to channel %s",
                            user_ctx.linked_channel_id,
                        )

        await session.flush()


async def _log_delivery(
    session: AsyncSession,
    user_id: int,
    event: Event,
    event_name: str,
    delivery_mode: str,
) -> None:
    await analytics_repo.log_event(
        session,
        event_name=event_name,
        source="scheduler",
        user_id=user_id,
        event_id=event.id,
        exchange=event.exchange,
        market_type=event.market_type.value,
        placement="listing_notification",
        properties={
            "delivery_mode": delivery_mode,
            "event_type": event.event_type.value,
            "score": event.score,
        },
    )
