from __future__ import annotations

import logging
import traceback
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import time

from sqlalchemy import delete, func, select

from app.db.models import AnalyticsEvent, CallbackToken, Delivery, TrackingSubscription, User
from app.metrics import active_users, detector_job_duration, job_errors, listings_detected
from app.services.announcements import AnnouncementMonitor, format_announcement_message
from app.services.delisting import DelistingNotifier
from app.services.detector import MarketDetector
from app.services.digest import DigestService
from app.services.notifier import EventNotifier
from app.services.price_alerts import PriceAlertService
from app.services.volume_spike import VolumeSpikeService

LOGGER = logging.getLogger(__name__)


def create_scheduler() -> AsyncIOScheduler:
    return AsyncIOScheduler(timezone=timezone.utc)


async def _notify_admin(bot: Bot | None, admin_id: int | None, job_name: str, exc: Exception) -> None:
    if bot is None or admin_id is None:
        return
    tb = traceback.format_exc()[-1000:]  # last 1000 chars
    try:
        await bot.send_message(
            admin_id,
            f"⚠️ <b>Сбой джоба</b> <code>{job_name}</code>\n"
            f"<code>{type(exc).__name__}: {exc}</code>\n\n"
            f"<pre>{tb}</pre>",
        )
    except Exception:
        LOGGER.exception("Failed to send admin alert")


async def _handle_job_failure(
    bot: Bot | None,
    admin_id: int | None,
    job_name: str,
    exc: Exception,
) -> None:
    job_errors.labels(job_id=job_name).inc()
    await _notify_admin(bot, admin_id, job_name, exc)


def schedule_detector_job(
    scheduler: AsyncIOScheduler,
    session_factory: async_sessionmaker[AsyncSession],
    detector: MarketDetector,
    notifier: EventNotifier,
    delisting_notifier: DelistingNotifier | None,
    interval_sec: int,
    bot: Bot | None = None,
    admin_id: int | None = None,
) -> None:
    async def _poll_markets() -> None:
        t0 = time.monotonic()
        events: list = []
        delistings: list = []

        # Phase 1: detect — commit snapshot FIRST, unconditionally.
        try:
            async with session_factory() as session:
                events, delistings = await detector.detect_new_events(session)
                if events:
                    for ev in events:
                        listings_detected.labels(
                            exchange=ev.exchange,
                            market_type=ev.market_type.value,
                        ).inc()
                await session.commit()
        except Exception as exc:
            LOGGER.exception("Detector job failed")
            await _handle_job_failure(bot, admin_id, "detector_poll", exc)
            events = []
            delistings = []
        finally:
            detector_job_duration.observe(time.monotonic() - t0)

        # Phase 2: listing notifications in a separate session.
        if events:
            try:
                async with session_factory() as session:
                    await notifier.process_events(session, events)
                    await session.commit()
            except Exception as exc:
                LOGGER.exception("Listing notification failed for %d events", len(events))
                await _handle_job_failure(bot, admin_id, "listing_notify", exc)

        # Phase 3: delisting notifications in a separate session.
        if delistings and delisting_notifier is not None:
            try:
                async with session_factory() as session:
                    await delisting_notifier.notify(session, delistings)
                    await session.commit()
            except Exception as exc:
                LOGGER.exception("Delisting notification failed for %d alerts", len(delistings))
                await _handle_job_failure(bot, admin_id, "delisting_notify", exc)

    scheduler.add_job(
        _poll_markets,
        trigger="interval",
        seconds=interval_sec,
        id="detector_poll",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc),
    )


def schedule_digest_job(
    scheduler: AsyncIOScheduler,
    digest_service: DigestService,
    bot: Bot | None = None,
    admin_id: int | None = None,
) -> None:
    async def _send_digests() -> None:
        try:
            await digest_service.send_pending_digests()
        except Exception as exc:
            LOGGER.exception("Digest job failed")
            await _handle_job_failure(bot, admin_id, "digest_send", exc)

    scheduler.add_job(
        _send_digests,
        trigger="interval",
        hours=1,
        id="digest_send",
        max_instances=1,
        coalesce=True,
    )


def schedule_announcement_job(
    scheduler: AsyncIOScheduler,
    monitor: AnnouncementMonitor,
    session_factory: async_sessionmaker[AsyncSession],
    bot: Bot,
    bot_admin_id: int | None = None,
) -> None:
    async def _check_announcements() -> None:
        try:
            new_items = await monitor.check_new()
            if not new_items:
                return
            from app.db.repo.users import list_all_users, is_user_paused
            from app.i18n import get_user_lang
            async with session_factory() as session:
                users = await list_all_users(session)
            for ann in new_items:
                LOGGER.info("New listing announcement from %s: %s", ann.source, ann.title)
                for user in users:
                    # Respect pause setting
                    if is_user_paused(user):
                        continue
                    # Respect enabled_exchanges filter
                    user_exchanges = (user.settings or {}).get("enabled_exchanges") or []
                    if user_exchanges and ann.source.lower() not in [e.lower() for e in user_exchanges]:
                        continue
                    lang = get_user_lang(user.settings)
                    text = format_announcement_message(ann, lang=lang)
                    try:
                        await bot.send_message(user.id, text, disable_web_page_preview=True)
                    except Exception:
                        LOGGER.warning("Failed to send announcement to user %s", user.id)
        except Exception as exc:
            LOGGER.exception("Announcement job failed")
            await _handle_job_failure(bot, bot_admin_id, "announcement_check", exc)

    scheduler.add_job(
        _check_announcements,
        trigger="interval",
        minutes=10,
        id="announcement_check",
        max_instances=1,
        coalesce=True,
    )


def schedule_price_alert_job(
    scheduler: AsyncIOScheduler,
    alert_service: PriceAlertService,
    bot: Bot | None = None,
    admin_id: int | None = None,
) -> None:
    async def _check_alerts() -> None:
        try:
            await alert_service.check_all()
        except Exception as exc:
            LOGGER.exception("Price alert job failed")
            await _handle_job_failure(bot, admin_id, "price_alert_check", exc)

    scheduler.add_job(
        _check_alerts,
        trigger="interval",
        minutes=5,
        id="price_alert_check",
        max_instances=1,
        coalesce=True,
    )


def schedule_volume_spike_job(
    scheduler: AsyncIOScheduler,
    spike_service: VolumeSpikeService,
    bot: Bot | None = None,
    admin_id: int | None = None,
) -> None:
    async def _check_spikes() -> None:
        try:
            await spike_service.check_all()
        except Exception as exc:
            LOGGER.exception("Volume spike job failed")
            await _handle_job_failure(bot, admin_id, "volume_spike_check", exc)

    scheduler.add_job(
        _check_spikes,
        trigger="interval",
        minutes=15,
        id="volume_spike_check",
        max_instances=1,
        coalesce=True,
    )


def schedule_cleanup_job(
    scheduler: AsyncIOScheduler,
    session_factory: async_sessionmaker[AsyncSession],
    bot: Bot | None = None,
    admin_id: int | None = None,
) -> None:
    """Delete stale DB rows every 6 hours to keep tables manageable."""

    async def _cleanup() -> None:
        try:
            now = datetime.now(timezone.utc)
            token_cutoff = now - timedelta(hours=24)
            delivery_cutoff = now - timedelta(days=90)
            analytics_cutoff = now - timedelta(days=90)
            tracking_cutoff = now - timedelta(days=30)

            async with session_factory() as session:
                r1 = await session.execute(
                    delete(CallbackToken).where(CallbackToken.created_at < token_cutoff)
                )
                r2 = await session.execute(
                    delete(Delivery).where(Delivery.sent_at < delivery_cutoff)
                )
                r3 = await session.execute(
                    delete(AnalyticsEvent).where(AnalyticsEvent.event_time < analytics_cutoff)
                )
                r4 = await session.execute(
                    delete(TrackingSubscription).where(
                        TrackingSubscription.sent_at.is_not(None),
                        TrackingSubscription.sent_at < tracking_cutoff,
                    )
                )
                await session.commit()

            totals = {
                "callback_tokens": r1.rowcount,
                "deliveries": r2.rowcount,
                "analytics_events": r3.rowcount,
                "tracking_subscriptions": r4.rowcount,
            }
            deleted_any = sum(totals.values())
            if deleted_any:
                LOGGER.info("Cleanup: %s", ", ".join(f"{v} {k}" for k, v in totals.items() if v))
        except Exception as exc:
            LOGGER.exception("Cleanup job failed")
            await _handle_job_failure(bot, admin_id, "cleanup", exc)

    scheduler.add_job(
        _cleanup,
        trigger="interval",
        hours=6,
        id="cleanup",
        max_instances=1,
        coalesce=True,
    )


def schedule_active_users_job(
    scheduler: AsyncIOScheduler,
    session_factory: async_sessionmaker[AsyncSession],
    bot: Bot | None = None,
    admin_id: int | None = None,
) -> None:
    async def _refresh_active_users() -> None:
        try:
            async with session_factory() as session:
                users_count = await session.scalar(select(func.count(User.id)))
            active_users.set(float(users_count or 0))
        except Exception as exc:
            LOGGER.exception("Active users refresh job failed")
            await _handle_job_failure(bot, admin_id, "active_users_refresh", exc)

    scheduler.add_job(
        _refresh_active_users,
        trigger="interval",
        minutes=5,
        id="active_users_refresh",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc),
    )
