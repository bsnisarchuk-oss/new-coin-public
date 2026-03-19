from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot.lang import preferred_lang
from app.config import Settings
from app.db.repo import price_alerts as alerts_repo
from app.db.repo import users as users_repo

router = Router()

_ALERT_RE = re.compile(
    r"^([A-Z0-9]{1,16})\s*([><])\s*([\d.]+)(?:\s+(\w+))?$",
    re.IGNORECASE,
)
_KNOWN_EXCHANGES = {"binance", "bybit", "okx", "mexc", "coinbase"}


def _text(key: str, lang: str, **kwargs: str | int | Decimal) -> str:
    ru = {
        "help": (
            "Формат: /alert <TICKER> >|< <ЦЕНА> [биржа]\n"
            "Пример: /alert BTC > 50000\n"
            "Пример: /alert ETH < 2000 bybit\n"
            "Биржи: binance, bybit, okx, mexc, coinbase\n\n"
            "/alerts — список активных алертов\n"
            "/unalert <ID> — удалить алерт"
        ),
        "invalid": "Неверный формат. Пример: /alert BTC > 50000",
        "invalid_price": "Неверное значение цены.",
        "unknown_exchange": "Неизвестная биржа: {exchange}. Доступны: {available}",
        "limit": "Достигнут лимит алертов (10). Удали старые через /unalert <ID>.",
        "created": (
            "✅ Алерт создан [ID {alert_id}]:\n"
            "{ticker}/USDT {sign} {threshold} на {exchange}\n"
            "Проверка каждые 5 минут."
        ),
        "empty": "Нет активных алертов. Создай через /alert BTC > 50000",
        "header": "📋 <b>Активные алерты:</b>",
        "footer": "\nУдалить: /unalert <ID>",
        "unalert.invalid": "Формат: /unalert <ID>  (ID можно посмотреть в /alerts)",
        "unalert.deleted": "Алерт [{alert_id}] удалён.",
        "unalert.missing": "Алерт [{alert_id}] не найден или уже неактивен.",
    }
    en = {
        "help": (
            "Format: /alert <TICKER> >|< <PRICE> [exchange]\n"
            "Example: /alert BTC > 50000\n"
            "Example: /alert ETH < 2000 bybit\n"
            "Exchanges: binance, bybit, okx, mexc, coinbase\n\n"
            "/alerts — list active alerts\n"
            "/unalert <ID> — delete an alert"
        ),
        "invalid": "Invalid format. Example: /alert BTC > 50000",
        "invalid_price": "Invalid price value.",
        "unknown_exchange": "Unknown exchange: {exchange}. Available: {available}",
        "limit": "Alert limit reached (10). Delete old ones via /unalert <ID>.",
        "created": (
            "✅ Alert created [ID {alert_id}]:\n"
            "{ticker}/USDT {sign} {threshold} on {exchange}\n"
            "Checked every 5 minutes."
        ),
        "empty": "No active alerts. Create one with /alert BTC > 50000",
        "header": "📋 <b>Active alerts:</b>",
        "footer": "\nDelete: /unalert <ID>",
        "unalert.invalid": "Format: /unalert <ID>  (see IDs in /alerts)",
        "unalert.deleted": "Alert [{alert_id}] deleted.",
        "unalert.missing": "Alert [{alert_id}] was not found or is already inactive.",
    }
    text = (en if lang == "en" else ru)[key]
    return text.format(**kwargs) if kwargs else text


@router.message(Command("alert"))
async def cmd_alert(
    message: Message,
    command: CommandObject,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return

    raw = (command.args or "").strip()
    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, message.from_user.id, settings)
        lang = preferred_lang(
            user.settings,
            telegram_lang_code=message.from_user.language_code,
        )
        if not raw:
            await session.commit()
            await message.answer(_text("help", lang))
            return

        match = _ALERT_RE.match(raw)
        if not match:
            await session.commit()
            await message.answer(_text("invalid", lang))
            return

        ticker = match.group(1).upper()
        sign = match.group(2)
        direction = "gt" if sign == ">" else "lt"
        try:
            threshold = Decimal(match.group(3))
        except InvalidOperation:
            await session.commit()
            await message.answer(_text("invalid_price", lang))
            return

        exchange_raw = (match.group(4) or "binance").strip().lower()
        if exchange_raw not in _KNOWN_EXCHANGES:
            available = ", ".join(sorted(_KNOWN_EXCHANGES))
            await session.commit()
            await message.answer(
                _text(
                    "unknown_exchange",
                    lang,
                    exchange=exchange_raw,
                    available=available,
                )
            )
            return

        alert = await alerts_repo.create_alert(
            session=session,
            user_id=user.id,
            ticker=ticker,
            direction=direction,
            threshold=threshold,
            exchange=exchange_raw,
        )
        await session.commit()

    if alert is None:
        await message.answer(_text("limit", lang))
        return

    await message.answer(
        _text(
            "created",
            lang,
            alert_id=alert.id,
            ticker=ticker,
            sign=sign,
            threshold=threshold,
            exchange=exchange_raw.capitalize(),
        )
    )


@router.message(Command("alerts"))
async def cmd_alerts(
    message: Message,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return

    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, message.from_user.id, settings)
        lang = preferred_lang(
            user.settings,
            telegram_lang_code=message.from_user.language_code,
        )
        active = await alerts_repo.list_active_alerts(session, user.id)
        await session.commit()

    if not active:
        await message.answer(_text("empty", lang))
        return

    lines = [_text("header", lang)]
    for alert in active:
        sign = ">" if alert.direction == "gt" else "<"
        exchange = (alert.exchange or "binance").capitalize()
        lines.append(f"[{alert.id}] {alert.ticker}/USDT {sign} {alert.threshold} — {exchange}")
    lines.append(_text("footer", lang))
    await message.answer("\n".join(lines))


@router.message(Command("unalert"))
async def cmd_unalert(
    message: Message,
    command: CommandObject,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return

    raw = (command.args or "").strip()
    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, message.from_user.id, settings)
        lang = preferred_lang(
            user.settings,
            telegram_lang_code=message.from_user.language_code,
        )
        if not raw.isdigit():
            await session.commit()
            await message.answer(_text("unalert.invalid", lang))
            return
        alert_id = int(raw)
        removed = await alerts_repo.deactivate_alert(session, user.id, alert_id)
        await session.commit()

    if removed:
        await message.answer(_text("unalert.deleted", lang, alert_id=alert_id))
    else:
        await message.answer(_text("unalert.missing", lang, alert_id=alert_id))
