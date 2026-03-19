from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Dispatcher
from aiogram.types import ErrorEvent, Message, Update

LOGGER = logging.getLogger(__name__)

from app.bot.handlers.admin import router as admin_router
from app.bot.handlers.alert import router as alert_router
from app.bot.handlers.lang import router as lang_router
from app.bot.handlers.analytics import router as analytics_router
from app.bot.handlers.callbacks import router as callbacks_router
from app.bot.handlers.channel import router as channel_router
from app.bot.handlers.digest import router as digest_router
from app.bot.handlers.export import router as export_router
from app.bot.handlers.filters import router as filters_router
from app.bot.handlers.help import router as help_router
from app.bot.handlers.history import router as history_router
from app.bot.handlers.menu import router as menu_router
from app.bot.handlers.pause import router as pause_router
from app.bot.handlers.preset import router as preset_router
from app.bot.handlers.start import router as start_router
from app.bot.handlers.status import router as status_router
from app.bot.handlers.top import router as top_router
from app.bot.handlers.watchlist import router as watchlist_router

_RATE_LIMIT = 20       # max requests per user
_RATE_WINDOW = 60.0    # within this many seconds


class RateLimitMiddleware(BaseMiddleware):
    """Allow at most _RATE_LIMIT messages per user per _RATE_WINDOW seconds."""

    def __init__(self) -> None:
        self._timestamps: dict[int, deque[float]] = defaultdict(deque)

    async def __call__(
        self,
        handler: Callable[[Update, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        msg: Message | None = getattr(event, "message", None)
        if msg is not None and msg.from_user is not None:
            user_id = msg.from_user.id
            now = time.monotonic()
            dq = self._timestamps[user_id]
            # Drop timestamps outside the window
            while dq and now - dq[0] > _RATE_WINDOW:
                dq.popleft()
            if len(dq) >= _RATE_LIMIT:
                from app.i18n import t
                tc = msg.from_user.language_code or ""
                _lang = "en" if tc.startswith("en") else "ru"
                await msg.answer(t("dispatcher.rate_limit", _lang))
                return
            dq.append(now)
        return await handler(event, data)


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()

    dp.update.outer_middleware(RateLimitMiddleware())

    @dp.error()
    async def error_handler(event: ErrorEvent) -> None:
        LOGGER.exception("Unhandled error: %s", event.exception)
        if event.update.message:
            from app.i18n import t
            msg = event.update.message
            tc = (msg.from_user.language_code or "") if msg.from_user else ""
            _lang = "en" if tc.startswith("en") else "ru"
            await msg.answer(
                t("dispatcher.internal_error", _lang)
            )

    dp.include_router(admin_router)
    dp.include_router(lang_router)
    dp.include_router(start_router)
    dp.include_router(menu_router)
    dp.include_router(help_router)
    dp.include_router(status_router)
    dp.include_router(filters_router)
    dp.include_router(watchlist_router)
    dp.include_router(pause_router)
    dp.include_router(digest_router)
    dp.include_router(history_router)
    dp.include_router(analytics_router)
    dp.include_router(top_router)
    dp.include_router(export_router)
    dp.include_router(channel_router)
    dp.include_router(alert_router)
    dp.include_router(preset_router)
    dp.include_router(callbacks_router)
    return dp
