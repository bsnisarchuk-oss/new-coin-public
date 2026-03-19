from __future__ import annotations

import asyncio
import logging
from decimal import Decimal

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import User
from app.db.repo import price_alerts as alerts_repo
from app.i18n import get_user_lang, t
from app.metrics import price_alerts_triggered
from app.services.enrich import EnrichmentService

LOGGER = logging.getLogger(__name__)


class PriceAlertService:
    def __init__(
        self,
        bot: Bot,
        session_factory: async_sessionmaker[AsyncSession],
        enrichment_service: EnrichmentService,
    ) -> None:
        self._bot = bot
        self._session_factory = session_factory
        self._enrichment = enrichment_service

    async def check_all(self) -> None:
        """Fetch prices for all active alerts and trigger conditions that are met."""
        async with self._session_factory() as session:
            alerts = await alerts_repo.list_all_active_alerts(session)
            if not alerts:
                return

            # Group by (ticker, exchange) to minimise API calls
            seen: dict[tuple[str, str], Decimal | None] = {}
            for alert in alerts:
                exchange = alert.exchange or "binance"
                key = (alert.ticker.upper(), exchange.lower())
                if key not in seen:
                    seen[key] = await self._fetch_price(alert.ticker, exchange)

            for alert in alerts:
                exchange = alert.exchange or "binance"
                key = (alert.ticker.upper(), exchange.lower())
                price = seen.get(key)
                if price is None:
                    continue
                if _condition_met(alert.direction, price, alert.threshold):
                    user_obj = await session.get(User, alert.user_id)
                    lang = get_user_lang(user_obj.settings if user_obj else None)
                    quote = "USD" if exchange.lower() == "coinbase" else "USDT"
                    text = _format_alert(alert.ticker, exchange, alert.direction, price, alert.threshold, quote=quote, lang=lang)
                    delivered = await self._send(alert.user_id, text)
                    if delivered:
                        await alerts_repo.mark_triggered(session, alert.id)
                        price_alerts_triggered.inc()

            await session.commit()

    async def _fetch_price(self, ticker: str, exchange: str) -> Decimal | None:
        # Coinbase trades against USD, not USDT
        quote = "USD" if exchange.lower() == "coinbase" else "USDT"
        symbol = f"{ticker.upper()}{quote}"
        try:
            enriched, _ = await self._enrichment.enrich_event(
                exchange=exchange,
                market_type="spot",
                symbol=symbol,
                base=ticker.upper(),
                quote=quote,
            )
            raw = enriched.get("price")
            if raw is not None:
                return Decimal(str(raw))
        except Exception:
            LOGGER.warning("Failed to fetch price for %s on %s", ticker, exchange)
        return None

    async def _send(self, user_id: int, text: str) -> bool:
        try:
            await self._bot.send_message(chat_id=user_id, text=text)
            return True
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                await self._bot.send_message(chat_id=user_id, text=text)
                return True
            except Exception:
                LOGGER.exception("Retry failed for price alert to user %s", user_id)
                return False
        except TelegramForbiddenError:
            LOGGER.warning("User %s blocked bot, skipping price alert", user_id)
            return False
        except TelegramBadRequest:
            LOGGER.exception("Bad request sending price alert to user %s", user_id)
            return False
        except Exception:
            LOGGER.exception("Unexpected error sending price alert to user %s", user_id)
            return False


def _condition_met(direction: str, price: Decimal, threshold: Decimal) -> bool:
    if direction == "gt":
        return price > threshold
    if direction == "lt":
        return price < threshold
    return False


def _format_alert(
    ticker: str, exchange: str, direction: str, price: Decimal, threshold: Decimal,
    quote: str = "USDT",
    lang: str = "ru",
) -> str:
    arrow = "📈" if direction == "gt" else "📉"
    sign = ">" if direction == "gt" else "<"
    return t(
        "alert.triggered", lang,
        arrow=arrow,
        ticker=ticker,
        quote=quote,
        exchange=exchange.capitalize(),
        price=f"{price:.4f}",
        sign=sign,
        threshold=f"{threshold:.4f}",
    )
