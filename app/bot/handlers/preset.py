from __future__ import annotations

import re

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot.lang import preferred_lang
from app.config import Settings
from app.db.repo import presets as presets_repo
from app.db.repo import users as users_repo
from app.services.filtering import normalize_filters

router = Router()

_NAME_RE = re.compile(r"^[\w\-]{1,32}$")


def _validate_name(raw: str) -> str | None:
    name = raw.strip()
    if _NAME_RE.match(name):
        return name
    return None


def _text(key: str, lang: str, **kwargs: str | int | bool) -> str:
    ru = {
        "help": (
            "Управление пресетами фильтров:\n"
            "/preset list — список пресетов\n"
            "/preset save <NAME> — сохранить текущие фильтры\n"
            "/preset load <NAME> — применить пресет\n"
            "/preset delete <NAME> — удалить пресет\n\n"
            "Имя: буквы, цифры, дефис, до 32 символов. Максимум 5 пресетов."
        ),
        "empty": "Нет сохранённых пресетов. Создай через /preset save NAME",
        "header": "📁 <b>Пресеты фильтров:</b>",
        "invalid_name": "Неверное имя. Используй буквы, цифры, дефис (до 32 символов).",
        "limit": "Достигнут лимит пресетов (5). Удали ненужный через /preset delete NAME",
        "saved": "✅ Пресет <b>{name}</b> сохранён.",
        "invalid_preset": "Неверное имя пресета.",
        "missing": "Пресет <b>{name}</b> не найден. Список: /preset list",
        "loaded": (
            "✅ Пресет <b>{name}</b> применён.\n"
            "Биржи: {exchanges}\n"
            "Рынки: {markets}\n"
            "Min score: {score} | Только USDT: {only_usdt}"
        ),
        "deleted": "Пресет <b>{name}</b> удалён.",
        "delete_missing": "Пресет <b>{name}</b> не найден.",
        "unknown": (
            "Неизвестная команда. Доступны: list, save, load, delete\n"
            "Пример: /preset save my-filter"
        ),
    }
    en = {
        "help": (
            "Filter preset management:\n"
            "/preset list — list saved presets\n"
            "/preset save <NAME> — save current filters\n"
            "/preset load <NAME> — apply a preset\n"
            "/preset delete <NAME> — delete a preset\n\n"
            "Name: letters, digits, dash, up to 32 characters. Maximum 5 presets."
        ),
        "empty": "No saved presets. Create one with /preset save NAME",
        "header": "📁 <b>Filter presets:</b>",
        "invalid_name": "Invalid name. Use letters, digits, dash (up to 32 characters).",
        "limit": "Preset limit reached (5). Delete one via /preset delete NAME",
        "saved": "✅ Preset <b>{name}</b> saved.",
        "invalid_preset": "Invalid preset name.",
        "missing": "Preset <b>{name}</b> was not found. List: /preset list",
        "loaded": (
            "✅ Preset <b>{name}</b> applied.\n"
            "Exchanges: {exchanges}\n"
            "Markets: {markets}\n"
            "Min score: {score} | USDT only: {only_usdt}"
        ),
        "deleted": "Preset <b>{name}</b> deleted.",
        "delete_missing": "Preset <b>{name}</b> was not found.",
        "unknown": (
            "Unknown command. Available: list, save, load, delete\n"
            "Example: /preset save my-filter"
        ),
    }
    text = (en if lang == "en" else ru)[key]
    return text.format(**kwargs) if kwargs else text


@router.message(Command("preset"))
async def cmd_preset(
    message: Message,
    command: CommandObject,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return

    args = (command.args or "").split(maxsplit=1)
    subcommand = args[0].lower() if args else ""

    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, message.from_user.id, settings)
        lang = preferred_lang(
            user.settings,
            telegram_lang_code=message.from_user.language_code,
        )

        if not subcommand:
            await session.commit()
            await message.answer(_text("help", lang))
            return

        if subcommand == "list":
            all_presets = await presets_repo.list_presets(session, user.id)
            await session.commit()
            if not all_presets:
                await message.answer(_text("empty", lang))
                return
            lines = [_text("header", lang)]
            for preset in all_presets:
                normalized = normalize_filters(preset.settings, settings)
                exchanges = ",".join(sorted(normalized.enabled_exchanges))
                markets = ",".join(sorted(normalized.enabled_market_types))
                lines.append(
                    f"• <b>{preset.name}</b> | {exchanges} | {markets} | "
                    f"score≥{normalized.min_score} | usdt={normalized.only_usdt}"
                )
            await message.answer("\n".join(lines))
            return

        if subcommand == "save":
            name_raw = args[1] if len(args) > 1 else ""
            name = _validate_name(name_raw)
            if not name:
                await session.commit()
                await message.answer(_text("invalid_name", lang))
                return
            filter_keys = {
                "enabled_exchanges",
                "enabled_market_types",
                "only_usdt",
                "min_score",
            }
            current_filters = {
                key: value
                for key, value in (user.settings or {}).items()
                if key in filter_keys
            }
            preset = await presets_repo.save_preset(session, user.id, name, current_filters)
            await session.commit()
            if preset is None:
                await message.answer(_text("limit", lang))
                return
            await message.answer(_text("saved", lang, name=name))
            return

        if subcommand == "load":
            name_raw = args[1] if len(args) > 1 else ""
            name = _validate_name(name_raw)
            if not name:
                await session.commit()
                await message.answer(_text("invalid_preset", lang))
                return
            preset = await presets_repo.load_preset(session, user.id, name)
            if preset is None:
                await session.commit()
                await message.answer(_text("missing", lang, name=name))
                return
            user.settings = users_repo.merge_user_settings(
                user.settings or {},
                preset.settings,
            )
            await session.commit()
            normalized = normalize_filters(preset.settings, settings)
            await message.answer(
                _text(
                    "loaded",
                    lang,
                    name=name,
                    exchanges=",".join(sorted(normalized.enabled_exchanges)),
                    markets=",".join(sorted(normalized.enabled_market_types)),
                    score=normalized.min_score,
                    only_usdt=normalized.only_usdt,
                )
            )
            return

        if subcommand == "delete":
            name_raw = args[1] if len(args) > 1 else ""
            name = _validate_name(name_raw)
            if not name:
                await session.commit()
                await message.answer(_text("invalid_preset", lang))
                return
            removed = await presets_repo.delete_preset(session, user.id, name)
            await session.commit()
            if removed:
                await message.answer(_text("deleted", lang, name=name))
            else:
                await message.answer(_text("delete_missing", lang, name=name))
            return

        await session.commit()
        await message.answer(_text("unknown", lang))
