from __future__ import annotations

import asyncio
import logging
import os
import re

from dotenv import load_dotenv
load_dotenv()

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from alembic import command
from alembic.config import Config as AlembicConfig

from app.bot.dispatcher import build_dispatcher
from app.config import Settings, load_settings
from app.db.session import close_engine, get_session_factory, init_engine
from app.exchanges.binance import BinanceConnector
from app.exchanges.bybit import BybitConnector
from app.exchanges.coinbase import CoinbaseConnector
from app.exchanges.mexc import MEXCConnector
from app.exchanges.okx import OKXConnector
from app.jobs.scheduler import (
    create_scheduler,
    schedule_announcement_job,
    schedule_active_users_job,
    schedule_cleanup_job,
    schedule_detector_job,
    schedule_digest_job,
    schedule_price_alert_job,
    schedule_volume_spike_job,
)
from app.health import set_readiness, start_health_server
from app.i18n import t
from app.logging_setup import setup_logging
from app.metrics import start_metrics_server
from app.services.arbitrage import ArbitrageService
from app.services.coingecko import CoinInfoService
from app.services.dedup import DedupService
from app.services.detector import MarketDetector
from app.services.delisting import DelistingNotifier
from app.services.digest import DigestService
from app.services.enrich import EnrichmentService
from app.services.notifier import EventNotifier
from app.services.price_alerts import PriceAlertService
from app.services.announcements import AnnouncementMonitor
from app.services.tracker import TrackerService
from app.services.volume_spike import VolumeSpikeService

LOGGER = logging.getLogger(__name__)


def _mask_db_url(url: str) -> str:
    return re.sub(r"(://[^:]+:)[^@]+(@)", r"\1***\2", url)


def run_migrations(database_url: str) -> None:
    LOGGER.info("Running migrations against %s", _mask_db_url(database_url))
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)
    try:
        command.upgrade(alembic_cfg, "head")
    except Exception as exc:
        LOGGER.critical("Migration failed, aborting startup: %s", exc, exc_info=True)
        raise SystemExit(1) from exc


def _build_bot_commands(lang: str) -> list[BotCommand]:
    return [
        BotCommand(command="start", description=t("commands.start", lang)),
        BotCommand(command="help", description=t("commands.help", lang)),
        BotCommand(command="status", description=t("commands.status", lang)),
        BotCommand(command="filters", description=t("commands.filters", lang)),
        BotCommand(command="watch", description=t("commands.watch", lang)),
        BotCommand(command="watchlist", description=t("commands.watchlist", lang)),
        BotCommand(command="unwatch", description=t("commands.unwatch", lang)),
        BotCommand(command="pause", description=t("commands.pause", lang)),
        BotCommand(command="digest", description=t("commands.digest", lang)),
        BotCommand(command="history", description=t("commands.history", lang)),
        BotCommand(command="analytics", description=t("commands.analytics", lang)),
        BotCommand(command="alert", description=t("commands.alert", lang)),
        BotCommand(command="alerts", description=t("commands.alerts", lang)),
        BotCommand(command="unalert", description=t("commands.unalert", lang)),
        BotCommand(command="preset", description=t("commands.preset", lang)),
        BotCommand(command="top", description=t("commands.top", lang)),
        BotCommand(command="export", description=t("commands.export", lang)),
        BotCommand(command="setchannel", description=t("commands.setchannel", lang)),
        BotCommand(command="unsetchannel", description=t("commands.unsetchannel", lang)),
        BotCommand(command="lang", description=t("commands.lang", lang)),
    ]


async def run(settings: Settings) -> None:
    set_readiness(False, phase="migrating")
    # Run Alembic migrations in a thread pool so that env.py can safely call
    # asyncio.run() / SelectorEventLoop without conflicting with the running loop
    await asyncio.get_running_loop().run_in_executor(
        None, run_migrations, settings.database_url
    )

    # fileConfig inside env.py resets root logger to WARN and disables existing
    # loggers — restore INFO level so the rest of the app logs are visible
    import logging as _logging
    _root = _logging.getLogger()
    _root.setLevel(_logging.INFO)
    for _lgr in list(_logging.Logger.manager.loggerDict.values()):
        if isinstance(_lgr, _logging.Logger):
            _lgr.disabled = False

    metrics_port = int(os.getenv("METRICS_PORT", "9090"))
    metrics_enabled = start_metrics_server(metrics_port)

    health_port = int(os.getenv("HEALTH_PORT", "8080"))
    health_runner = await start_health_server(health_port)
    set_readiness(False, phase="starting_services")

    init_engine(settings.database_url)
    session_factory = get_session_factory()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher()

    await bot.set_my_commands(_build_bot_commands("ru"))
    await bot.set_my_commands(_build_bot_commands("ru"), language_code="ru")
    await bot.set_my_commands(_build_bot_commands("en"), language_code="en")

    enrichment_service = EnrichmentService(settings)
    await enrichment_service.start()
    arbitrage_service = ArbitrageService()
    await arbitrage_service.start()
    coin_info_service = CoinInfoService()
    await coin_info_service.start()
    dedup_service = DedupService(settings)
    scheduler = create_scheduler()

    tracker_service = TrackerService(
        bot=bot,
        scheduler=scheduler,
        session_factory=session_factory,
        enrichment_service=enrichment_service,
    )
    digest_service = DigestService(bot=bot, session_factory=session_factory)
    volume_spike_service = VolumeSpikeService(bot=bot, session_factory=session_factory)
    price_alert_service = PriceAlertService(
        bot=bot,
        session_factory=session_factory,
        enrichment_service=enrichment_service,
    )
    delisting_notifier = DelistingNotifier(bot=bot)

    detector = MarketDetector(
        connectors=[BinanceConnector(), BybitConnector(), CoinbaseConnector(), OKXConnector(), MEXCConnector()],
        bootstrap_on_empty=settings.bootstrap_on_empty,
    )
    notifier = EventNotifier(
        bot=bot,
        settings=settings,
        enrichment_service=enrichment_service,
        dedup_service=dedup_service,
        arbitrage_service=arbitrage_service,
        coin_info_service=coin_info_service,
    )
    schedule_detector_job(
        scheduler=scheduler,
        session_factory=session_factory,
        detector=detector,
        notifier=notifier,
        delisting_notifier=delisting_notifier,
        interval_sec=settings.poll_interval_sec,
        bot=bot,
        admin_id=settings.admin_id,
    )
    schedule_digest_job(scheduler=scheduler, digest_service=digest_service, bot=bot, admin_id=settings.admin_id)
    schedule_price_alert_job(scheduler=scheduler, alert_service=price_alert_service, bot=bot, admin_id=settings.admin_id)
    schedule_announcement_job(
        scheduler=scheduler,
        monitor=AnnouncementMonitor(session_factory=session_factory),
        session_factory=session_factory,
        bot=bot,
        bot_admin_id=settings.admin_id,
    )
    schedule_volume_spike_job(
        scheduler=scheduler,
        spike_service=volume_spike_service,
        bot=bot,
        admin_id=settings.admin_id,
    )
    schedule_cleanup_job(
        scheduler=scheduler,
        session_factory=session_factory,
        bot=bot,
        admin_id=settings.admin_id,
    )
    schedule_active_users_job(
        scheduler=scheduler,
        session_factory=session_factory,
        bot=bot,
        admin_id=settings.admin_id,
    )

    scheduler.start()
    await tracker_service.restore_pending_jobs()
    set_readiness(True, phase="running")

    # Delete any previously registered webhook so long-polling works
    await bot.delete_webhook(drop_pending_updates=True)

    LOGGER.info("Bot started (metrics_enabled=%s)", metrics_enabled)
    print(">>> Bot started — polling for updates <<<", flush=True)
    try:
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query"],
            settings=settings,
            session_factory=session_factory,
            tracker_service=tracker_service,
        )
    finally:
        set_readiness(False, phase="stopping")
        scheduler.shutdown(wait=True)
        await enrichment_service.close()
        await arbitrage_service.close()
        await coin_info_service.close()
        await bot.session.close()
        await close_engine()
        await health_runner.cleanup()
        LOGGER.info("Bot stopped")


if __name__ == "__main__":
    _settings = load_settings()
    setup_logging()
    try:
        asyncio.run(run(_settings))
    except (KeyboardInterrupt, SystemExit):
        pass
