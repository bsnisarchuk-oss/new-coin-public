from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Event, TrackingSubscription, User
from app.i18n import get_user_lang, t
from app.services.enrich import EnrichmentService

LOGGER = logging.getLogger(__name__)

_BLOCKS = "▁▂▃▄▅▆▇█"


def sparkline(prices: list[float]) -> str:
    """Render a Unicode sparkline from a price series (oldest → newest)."""
    if not prices:
        return ""
    lo, hi = min(prices), max(prices)
    spread = hi - lo
    n = len(_BLOCKS) - 1
    chars = [
        _BLOCKS[n // 2 if spread == 0 else round((p - lo) / spread * n)]
        for p in prices
    ]
    return "".join(chars)


class TrackerService:
    def __init__(
        self,
        bot: Bot,
        scheduler: AsyncIOScheduler,
        session_factory: async_sessionmaker[AsyncSession],
        enrichment_service: EnrichmentService,
    ) -> None:
        self._bot = bot
        self._scheduler = scheduler
        self._session_factory = session_factory
        self._enrichment = enrichment_service

    async def restore_pending_jobs(self) -> None:
        """Reschedule unsent tracking subscriptions that survived a bot restart."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(TrackingSubscription).where(TrackingSubscription.sent_at.is_(None))
            )
            pending = result.scalars().all()

        if not pending:
            return

        now = datetime.now(timezone.utc)
        for sub in pending:
            run_at = sub.scheduled_for
            if run_at <= now:
                # Job is overdue — send after a short delay so the bot finishes startup
                run_at = now + timedelta(seconds=15)
            self._scheduler.add_job(
                self.send_tracking_report,
                trigger="date",
                run_date=run_at,
                kwargs={"subscription_id": str(sub.id)},
                id=f"track:{sub.id}",
                replace_existing=True,
                misfire_grace_time=300,
            )

        LOGGER.info("Restored %d pending tracking job(s) after restart", len(pending))

    async def subscribe_24h(
        self, session: AsyncSession, user_id: int, event: Event
    ) -> list[int]:
        scheduled: list[int] = []
        for minutes in (15, 60, 240, 1440):
            already_exists = await session.execute(
                select(TrackingSubscription.id).where(
                    TrackingSubscription.user_id == user_id,
                    TrackingSubscription.event_id == event.id,
                    TrackingSubscription.report_after_minutes == minutes,
                    TrackingSubscription.sent_at.is_(None),
                )
            )
            if already_exists.scalar_one_or_none() is not None:
                continue

            run_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
            sub = TrackingSubscription(
                user_id=user_id,
                event_id=event.id,
                exchange=event.exchange,
                market_type=event.market_type,
                symbol_base=event.symbol_base,
                symbol_quote=event.symbol_quote,
                report_after_minutes=minutes,
                scheduled_for=run_at,
            )
            session.add(sub)
            await session.flush()
            self._scheduler.add_job(
                self.send_tracking_report,
                trigger="date",
                run_date=run_at,
                kwargs={"subscription_id": str(sub.id)},
                id=f"track:{sub.id}",
                replace_existing=True,
                misfire_grace_time=300,
            )
            scheduled.append(minutes)
        return scheduled

    async def send_tracking_report(self, subscription_id: str) -> None:
        try:
            sub_id = uuid.UUID(subscription_id)
        except ValueError:
            LOGGER.warning("Invalid tracking subscription id: %s", subscription_id)
            return

        async with self._session_factory() as session:
            sub = await session.get(TrackingSubscription, sub_id)
            if sub is None or sub.sent_at is not None:
                return
            event = await session.get(Event, sub.event_id)
            if event is None:
                return

            symbol = f"{sub.symbol_base}{sub.symbol_quote}"
            enriched, flags = await self._enrichment.enrich_event(
                exchange=sub.exchange,
                market_type=sub.market_type.value,
                symbol=symbol,
                base=sub.symbol_base,
                quote=sub.symbol_quote,
            )
            initial_price = (event.enriched or {}).get("price")
            user_obj = await session.get(User, sub.user_id)
            lang = get_user_lang(user_obj.settings if user_obj else None)
            klines = await self._enrichment.fetch_klines(
                exchange=sub.exchange,
                symbol=f"{sub.symbol_base}{sub.symbol_quote}",
                market_type=sub.market_type.value,
                base=sub.symbol_base,
                quote=sub.symbol_quote,
                minutes=sub.report_after_minutes,
            )
            text = _format_tracking_report(
                exchange=sub.exchange,
                base=sub.symbol_base,
                quote=sub.symbol_quote,
                minutes=sub.report_after_minutes,
                enriched=enriched,
                flags=flags,
                initial_price=initial_price,
                klines=klines,
                lang=lang,
            )
            try:
                await self._bot.send_message(chat_id=sub.user_id, text=text)
                sub.sent_at = datetime.now(timezone.utc)
                await session.commit()
            except TelegramRetryAfter as e:
                LOGGER.warning(
                    "Flood control for tracking report %s, retrying after %ss",
                    sub.id,
                    e.retry_after,
                )
                await asyncio.sleep(e.retry_after)
                try:
                    await self._bot.send_message(chat_id=sub.user_id, text=text)
                    sub.sent_at = datetime.now(timezone.utc)
                    await session.commit()
                except Exception:
                    LOGGER.exception(
                        "Retry after flood control failed for tracking report %s", sub.id
                    )
            except TelegramForbiddenError:
                LOGGER.warning(
                    "Failed to send tracking report %s: user %s blocked bot",
                    sub.id,
                    sub.user_id,
                )
            except TelegramBadRequest:
                LOGGER.exception(
                    "Failed to send tracking report %s to user %s",
                    sub.id,
                    sub.user_id,
                )


def _format_tracking_report(
    exchange: str,
    base: str,
    quote: str,
    minutes: int,
    enriched: dict,
    flags: list[str],
    initial_price: float | None = None,
    klines: list[float] | None = None,
    lang: str = "ru",
) -> str:
    current_price = enriched.get("price")

    # Calculate % change from listing price
    price_change_str = ""
    if initial_price is not None and current_price is not None:
        try:
            pct = (float(current_price) - float(initial_price)) / float(initial_price) * 100
            arrow = "🚀" if pct >= 10 else ("📈" if pct > 0 else ("📉" if pct < 0 else "➡️"))
            sign = "+" if pct >= 0 else ""
            price_change_str = "\n" + t("tracker.change", lang, arrow=arrow, sign=sign, pct=pct)
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    metrics = []
    if current_price is not None:
        metrics.append(f"Price: {current_price}")
    if enriched.get("volume_5m") is not None:
        metrics.append(f"Vol(5m): {round(float(enriched['volume_5m']), 4)}")
    if enriched.get("spread") is not None:
        metrics.append(f"Spread: {round(float(enriched['spread']) * 100, 4)}%")
    metrics_text = " | ".join(metrics) if metrics else t("tracker.no_metrics", lang)
    flags_text = ", ".join(flags) if flags else "-"

    # Sparkline chart
    chart_str = ""
    if klines:
        chart = sparkline(klines)
        if minutes <= 15:
            interval_label = "1m"
        elif minutes <= 240:
            interval_label = "5m"
        else:
            interval_label = "30m"
        chart_str = f"\n📊 {chart}  ({interval_label}×{len(klines)})"

    # Human-readable window label
    if minutes >= 1440:
        window_label = f"{minutes // 1440}d"
    elif minutes >= 60:
        window_label = f"{minutes // 60}h"
    else:
        window_label = f"{minutes}m"

    return (
        f"📈 TRACK {window_label}: {base}/{quote} — {exchange.capitalize()}\n"
        f"{metrics_text}{price_change_str}{chart_str}\n"
        f"Flags: {flags_text}"
    )

