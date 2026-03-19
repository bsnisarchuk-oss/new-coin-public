"""Simulate a listing event and send it through the full notification pipeline.

Usage:
    python -m app.scripts.simulate_event           # fake SIMxxxx/USDT
    python -m app.scripts.simulate_event BTC USDT  # real symbol (shows arb prices)
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from dotenv import load_dotenv
load_dotenv()

from app.config import load_settings
from app.db.models import Event, EventType, MarketType
from app.db.session import close_engine, get_session_factory, init_engine
from app.logging_setup import setup_logging
from app.services.arbitrage import ArbitrageService
from app.services.dedup import DedupService, build_event_key
from app.services.enrich import EnrichmentService
from app.services.notifier import EventNotifier, format_event_message


async def run(base: str, quote: str) -> None:
    settings = load_settings()
    setup_logging()
    init_engine(settings.database_url)
    session_factory = get_session_factory()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    enrichment_service = EnrichmentService(settings)
    await enrichment_service.start()

    arbitrage_service = ArbitrageService()
    await arbitrage_service.start()

    notifier = EventNotifier(
        bot=bot,
        settings=settings,
        enrichment_service=enrichment_service,
        dedup_service=DedupService(settings),
        arbitrage_service=arbitrage_service,
    )

    # Append timestamp so every simulate run bypasses dedup
    ts = int(datetime.now(timezone.utc).timestamp())
    event_key = build_event_key(
        exchange="binance",
        event_type=EventType.SPOT_LISTING,
        market_type=MarketType.SPOT,
        base=base,
        quote=quote,
    ) + f":sim{ts}"

    async with session_factory() as session:
        event = Event(
            exchange="binance",
            event_type=EventType.SPOT_LISTING,
            market_type=MarketType.SPOT,
            symbol_base=base,
            symbol_quote=quote,
            first_seen_at=datetime.now(timezone.utc),
            pairs=[f"{base}{quote}"],
            event_key=event_key,
            meta={"source": "simulate_script"},
            enriched={},
            score=0,
            flags=[],
        )
        session.add(event)
        await session.flush()
        await notifier.process_events(session, [event])
        await session.commit()

    # Print preview to stdout so you can check format without receiving Telegram msg
    print("\n--- MESSAGE PREVIEW ---")
    print(format_event_message(event))
    print("-----------------------\n")
    print(f"Simulated event sent: {base}/{quote}")

    await enrichment_service.close()
    await arbitrage_service.close()
    await bot.session.close()
    await close_engine()


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) >= 2:
        _base, _quote = args[0].upper(), args[1].upper()
    else:
        # Fake ticker — won't have real prices, good for delivery pipeline check
        _base = f"SIM{int(datetime.now(timezone.utc).timestamp()) % 10000}"
        _quote = "USDT"

    asyncio.run(run(_base, _quote))
