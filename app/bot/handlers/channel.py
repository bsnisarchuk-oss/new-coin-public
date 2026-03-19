from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot.lang import preferred_lang
from app.config import Settings
from app.db.repo.users import get_or_create_user

router = Router()
LOGGER = logging.getLogger(__name__)


def _text(key: str, lang: str, **kwargs: int | str) -> str:
    ru = {
        "usage": (
            "Использование: <code>/setchannel -100xxxxxxxxxx</code>\n\n"
            "Как получить ID канала:\n"
            "1. Добавьте бота в канал как администратора\n"
            "2. Перешлите любое сообщение из канала боту @userinfobot\n"
            "3. Скопируйте Chat ID (начинается с -100)"
        ),
        "invalid": "Неверный формат. ID канала должен быть числом, например: <code>-1001234567890</code>",
        "probe": "✅ Канал успешно подключён к боту!",
        "forbidden": "Бот не является администратором этого канала. Добавьте бота как администратора и попробуйте снова.",
        "bad_request": "Не удалось подключить канал: <code>{error}</code>",
        "linked": "✅ Канал <code>{channel_id}</code> подключён. Все листинги будут дублироваться туда.",
        "unlinked": "Канал отключён. Листинги больше не будут дублироваться.",
    }
    en = {
        "usage": (
            "Usage: <code>/setchannel -100xxxxxxxxxx</code>\n\n"
            "How to get the channel ID:\n"
            "1. Add the bot to the channel as an admin\n"
            "2. Forward any channel message to @userinfobot\n"
            "3. Copy the Chat ID (it starts with -100)"
        ),
        "invalid": "Invalid format. Channel ID must be a number, for example: <code>-1001234567890</code>",
        "probe": "✅ Channel linked successfully!",
        "forbidden": "The bot is not an admin in this channel. Add it as an admin and try again.",
        "bad_request": "Failed to link the channel: <code>{error}</code>",
        "linked": "✅ Channel <code>{channel_id}</code> linked. All listings will be forwarded there.",
        "unlinked": "Channel unlinked. Listings will no longer be forwarded there.",
    }
    text = (en if lang == "en" else ru)[key]
    return text.format(**kwargs) if kwargs else text


@router.message(Command("setchannel"))
async def cmd_setchannel(
    message: Message,
    bot: Bot,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return
    parts = (message.text or "").split(maxsplit=1)
    async with session_factory() as session:
        user = await get_or_create_user(session, message.from_user.id, settings)
        lang = preferred_lang(
            user.settings,
            telegram_lang_code=message.from_user.language_code,
        )
        await session.commit()
    if len(parts) < 2:
        await message.answer(_text("usage", lang))
        return

    raw = parts[1].strip()
    try:
        channel_id = int(raw)
    except ValueError:
        await message.answer(_text("invalid", lang))
        return

    try:
        probe = await bot.send_message(channel_id, _text("probe", lang))
        await bot.delete_message(channel_id, probe.message_id)
    except TelegramForbiddenError:
        await message.answer(_text("forbidden", lang))
        return
    except TelegramBadRequest as exc:
        await message.answer(_text("bad_request", lang, error=str(exc)))
        return

    async with session_factory() as session:
        user = await get_or_create_user(session, message.from_user.id, settings)
        settings_copy = dict(user.settings or {})
        settings_copy["linked_channel_id"] = channel_id
        user.settings = settings_copy
        await session.commit()

    await message.answer(_text("linked", lang, channel_id=channel_id))


@router.message(Command("unsetchannel"))
async def cmd_unsetchannel(
    message: Message,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return
    async with session_factory() as session:
        user = await get_or_create_user(session, message.from_user.id, settings)
        lang = preferred_lang(
            user.settings,
            telegram_lang_code=message.from_user.language_code,
        )
        settings_copy = dict(user.settings or {})
        settings_copy.pop("linked_channel_id", None)
        user.settings = settings_copy
        await session.commit()

    await message.answer(_text("unlinked", lang))
