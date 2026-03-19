"""Admin-only commands: /admin stats|broadcast|user."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot.lang import guess_lang
from app.config import Settings
from app.db.models import Delivery, Event, User
from app.db.repo import users as users_repo

LOGGER = logging.getLogger(__name__)

router = Router()


def _text(key: str, lang: str, **kwargs: str | int) -> str:
    ru = {
        "help": (
            "<b>🔧 Admin panel</b>\n\n"
            "<code>/admin stats</code> — статистика бота\n"
            "<code>/admin broadcast &lt;текст&gt;</code> — рассылка всем пользователям\n"
            "<code>/admin user &lt;id&gt;</code> — инфо о пользователе\n"
        ),
        "usage.broadcast": "Использование: <code>/admin broadcast &lt;текст&gt;</code>",
        "usage.user": "Использование: <code>/admin user &lt;user_id&gt;</code>",
        "stats": (
            "<b>📊 Статистика бота</b>\n\n"
            "<b>Пользователи:</b>\n"
            "  Всего: {total_users}\n"
            "  Новых сегодня: {new_today}\n"
            "  Активных за 24ч: {active_24h}\n\n"
            "<b>Листинги:</b>\n"
            "  Всего событий: {total_events}\n"
            "  За последние 24ч: {events_24h}"
        ),
        "broadcast.empty": "Нет пользователей для рассылки.",
        "broadcast.body": "📢 <b>Сообщение от администратора:</b>\n\n{text}",
        "broadcast.done": "✅ Рассылка завершена\nОтправлено: {sent} | Ошибок: {failed}",
        "user.missing": "Пользователь <code>{user_id}</code> не найден.",
        "user.unknown": "неизвестно",
        "user.info": (
            "<b>👤 Пользователь {user_id}</b>\n\n"
            "Зарегистрирован: {created}\n"
            "Уведомлений отправлено: {deliveries_total}\n\n"
            "<b>Настройки:</b>\n"
            "  Биржи: {exchanges}\n"
            "  Рынки: {markets}\n"
            "  Только USDT: {only_usdt}\n"
            "  Min score: {min_score}\n"
            "  Дайджест: {digest}\n"
            "  Пауза: {paused}"
        ),
        "digest.on": "вкл",
        "digest.off": "выкл",
        "paused.yes": "да",
        "paused.no": "нет",
    }
    en = {
        "help": (
            "<b>🔧 Admin panel</b>\n\n"
            "<code>/admin stats</code> — bot statistics\n"
            "<code>/admin broadcast &lt;text&gt;</code> — broadcast to all users\n"
            "<code>/admin user &lt;id&gt;</code> — user details\n"
        ),
        "usage.broadcast": "Usage: <code>/admin broadcast &lt;text&gt;</code>",
        "usage.user": "Usage: <code>/admin user &lt;user_id&gt;</code>",
        "stats": (
            "<b>📊 Bot statistics</b>\n\n"
            "<b>Users:</b>\n"
            "  Total: {total_users}\n"
            "  New today: {new_today}\n"
            "  Active over 24h: {active_24h}\n\n"
            "<b>Listings:</b>\n"
            "  Total events: {total_events}\n"
            "  Over the last 24h: {events_24h}"
        ),
        "broadcast.empty": "There are no users to broadcast to.",
        "broadcast.body": "📢 <b>Message from the administrator:</b>\n\n{text}",
        "broadcast.done": "✅ Broadcast completed\nSent: {sent} | Errors: {failed}",
        "user.missing": "User <code>{user_id}</code> was not found.",
        "user.unknown": "unknown",
        "user.info": (
            "<b>👤 User {user_id}</b>\n\n"
            "Registered: {created}\n"
            "Notifications sent: {deliveries_total}\n\n"
            "<b>Settings:</b>\n"
            "  Exchanges: {exchanges}\n"
            "  Markets: {markets}\n"
            "  USDT only: {only_usdt}\n"
            "  Min score: {min_score}\n"
            "  Digest: {digest}\n"
            "  Pause: {paused}"
        ),
        "digest.on": "on",
        "digest.off": "off",
        "paused.yes": "yes",
        "paused.no": "no",
    }
    text = (en if lang == "en" else ru)[key]
    return text.format(**kwargs) if kwargs else text


def _is_admin(message: Message, settings: Settings) -> bool:
    if message.from_user is None:
        return False
    return settings.admin_id is not None and message.from_user.id == settings.admin_id


@router.message(Command("admin"))
async def cmd_admin(
    message: Message,
    command: CommandObject,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if not _is_admin(message, settings):
        return
    lang = guess_lang(message.from_user.language_code if message.from_user else None)
    args = (command.args or "").strip()
    subcommand, _, rest = args.partition(" ")

    if subcommand == "stats":
        await _handle_stats(message, session_factory, lang)
    elif subcommand == "broadcast":
        text = rest.strip()
        if not text:
            await message.answer(_text("usage.broadcast", lang))
            return
        await _handle_broadcast(message, text, session_factory, lang)
    elif subcommand == "user":
        uid_str = rest.strip()
        if not uid_str.lstrip("-").isdigit():
            await message.answer(_text("usage.user", lang))
            return
        await _handle_user(message, int(uid_str), session_factory, lang)
    else:
        await message.answer(_text("help", lang))


async def _handle_stats(
    message: Message,
    session_factory: async_sessionmaker,
    lang: str,
) -> None:
    now = datetime.now(timezone.utc)
    since_24h = now - timedelta(hours=24)
    since_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    async with session_factory() as session:
        total_users = int((await session.execute(select(func.count(User.id)))).scalar_one() or 0)
        new_today = int(
            (await session.execute(select(func.count(User.id)).where(User.created_at >= since_today))).scalar_one()
            or 0
        )
        active_24h = int(
            (
                await session.execute(
                    select(func.count(func.distinct(Delivery.user_id))).where(
                        Delivery.sent_at >= since_24h
                    )
                )
            ).scalar_one()
            or 0
        )
        total_events = int((await session.execute(select(func.count(Event.id)))).scalar_one() or 0)
        events_24h = int(
            (await session.execute(select(func.count(Event.id)).where(Event.first_seen_at >= since_24h))).scalar_one()
            or 0
        )
        await session.commit()

    await message.answer(
        _text(
            "stats",
            lang,
            total_users=total_users,
            new_today=new_today,
            active_24h=active_24h,
            total_events=total_events,
            events_24h=events_24h,
        )
    )


async def _handle_broadcast(
    message: Message,
    text: str,
    session_factory: async_sessionmaker,
    lang: str,
) -> None:
    async with session_factory() as session:
        users = await users_repo.list_all_users(session)

    if not users:
        await message.answer(_text("broadcast.empty", lang))
        return

    sent = 0
    failed = 0
    broadcast_text = _text("broadcast.body", lang, text=text)

    for user in users:
        try:
            await message.bot.send_message(chat_id=user.id, text=broadcast_text)  # type: ignore[union-attr]
            sent += 1
            await asyncio.sleep(0.05)
        except TelegramRetryAfter as exc:
            LOGGER.warning("Broadcast: flood control, retrying after %ss", exc.retry_after)
            await asyncio.sleep(exc.retry_after)
            try:
                await message.bot.send_message(chat_id=user.id, text=broadcast_text)  # type: ignore[union-attr]
                sent += 1
            except Exception as retry_exc:
                LOGGER.warning("Broadcast retry failed for user %s: %s", user.id, retry_exc)
                failed += 1
        except TelegramForbiddenError:
            LOGGER.debug("Broadcast: user %s blocked bot", user.id)
            failed += 1
        except TelegramBadRequest as exc:
            LOGGER.warning("Broadcast: bad request for user %s: %s", user.id, exc)
            failed += 1
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.warning("Broadcast: failed for user %s: %s", user.id, exc)
            failed += 1

    await message.answer(_text("broadcast.done", lang, sent=sent, failed=failed))


async def _handle_user(
    message: Message,
    user_id: int,
    session_factory: async_sessionmaker,
    lang: str,
) -> None:
    async with session_factory() as session:
        user = await session.get(User, user_id)
        if user is None:
            await message.answer(_text("user.missing", lang, user_id=user_id))
            return

        deliveries_total = int(
            (await session.execute(select(func.count(Delivery.id)).where(Delivery.user_id == user_id))).scalar_one()
            or 0
        )
        await session.commit()

    settings = user.settings or {}
    paused = users_repo.is_user_paused(user)
    digest = users_repo.is_user_in_digest_mode(user)
    created_str = (
        user.created_at.strftime("%Y-%m-%d %H:%M UTC")
        if user.created_at
        else _text("user.unknown", lang)
    )
    await message.answer(
        _text(
            "user.info",
            lang,
            user_id=user_id,
            created=created_str,
            deliveries_total=deliveries_total,
            exchanges=", ".join(settings.get("enabled_exchanges", [])),
            markets=", ".join(settings.get("enabled_market_types", [])),
            only_usdt=settings.get("only_usdt", False),
            min_score=settings.get("min_score", 0),
            digest=_text("digest.on", lang) if digest else _text("digest.off", lang),
            paused=_text("paused.yes", lang) if paused else _text("paused.no", lang),
        )
    )
