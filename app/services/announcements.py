from __future__ import annotations

import logging
from typing import Any

import aiohttp
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.repo import state as state_repo
from app.i18n import t

LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=15)
_STATE_SERVICE = "announcements"
_STATE_KEY = "listing_monitor"
_STATE_TRIM_SIZE = 300
_STATE_MAX_SIZE = 500

# Keywords that indicate a new listing announcement
_LISTING_KEYWORDS = [
    "will list", "lists", "listing", "добавит", "листинг",
]

_SOURCES = [
    {
        "name": "Binance",
        "url": (
            "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
            "?type=1&pageNo=1&pageSize=20"
        ),
        "extractor": "_parse_binance",
    },
    {
        "name": "OKX",
        "url": "https://www.okx.com/v2/support/home/web?type=1&page=1&pageSize=20",
        "extractor": "_parse_okx",
    },
]


class Announcement:
    __slots__ = ("source", "article_id", "title", "url")

    def __init__(self, source: str, article_id: str, title: str, url: str) -> None:
        self.source = source
        self.article_id = article_id
        self.title = title
        self.url = url


class AnnouncementMonitor:
    """Polls exchange announcement pages and detects new listing announcements."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def check_new(self) -> list[Announcement]:
        """Return new listing announcements since last call.

        On the very first call, seeds _seen_ids without returning anything
        (bootstrap — same pattern as the market snapshot detector).
        """
        initialized, seen_ids_list, seen_ids = await self._load_state()
        new_announcements: list[Announcement] = []
        all_fetched: list[Announcement] = []

        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            for source in _SOURCES:
                try:
                    items = await self._fetch(session, source)
                    all_fetched.extend(items)
                except Exception:
                    LOGGER.exception("Failed to fetch announcements from %s", source["name"])

        if not initialized:
            # Seed — mark all current as seen, don't notify
            for ann in all_fetched:
                if ann.article_id not in seen_ids:
                    seen_ids.add(ann.article_id)
                    seen_ids_list.append(ann.article_id)
            await self._save_state(True, seen_ids_list)
            LOGGER.info("Announcement monitor bootstrapped with %d articles", len(seen_ids_list))
            return []

        for ann in all_fetched:
            if ann.article_id not in seen_ids:
                if _is_listing_announcement(ann.title):
                    new_announcements.append(ann)
                seen_ids.add(ann.article_id)
                seen_ids_list.append(ann.article_id)

        # Keep memory bounded
        if len(seen_ids_list) > _STATE_MAX_SIZE:
            seen_ids_list = seen_ids_list[-_STATE_TRIM_SIZE:]

        await self._save_state(True, seen_ids_list)

        return new_announcements

    async def _load_state(self) -> tuple[bool, list[str], set[str]]:
        async with self._session_factory() as session:
            payload = await state_repo.get_payload(session, _STATE_SERVICE, _STATE_KEY)

        raw_ids = payload.get("seen_ids", []) if payload else []
        seen_ids_list = [str(item) for item in raw_ids if item]
        return bool(payload and payload.get("initialized")), seen_ids_list, set(seen_ids_list)

    async def _save_state(self, initialized: bool, seen_ids_list: list[str]) -> None:
        async with self._session_factory() as session:
            await state_repo.set_payload(
                session,
                _STATE_SERVICE,
                _STATE_KEY,
                {
                    "initialized": initialized,
                    "seen_ids": seen_ids_list,
                },
            )
            await session.commit()

    async def _fetch(
        self, session: aiohttp.ClientSession, source: dict[str, Any]
    ) -> list[Announcement]:
        extractor = getattr(self, source["extractor"])
        async with session.get(source["url"]) as resp:
            resp.raise_for_status()
            payload = await resp.json(content_type=None)
        return extractor(source["name"], payload)

    @staticmethod
    def _parse_binance(source: str, payload: dict) -> list[Announcement]:
        articles = (payload.get("data") or {}).get("articles") or []
        result = []
        for article in articles:
            if not isinstance(article, dict):
                continue
            article_id = str(article.get("id", ""))
            title = str(article.get("title", ""))
            code = str(article.get("code", ""))
            url = f"https://www.binance.com/en/support/announcement/{code}" if code else ""
            if article_id:
                result.append(Announcement(source, article_id, title, url))
        return result

    @staticmethod
    def _parse_okx(source: str, payload: dict) -> list[Announcement]:
        articles = (payload.get("data") or {}).get("list") or []
        result = []
        for article in articles:
            if not isinstance(article, dict):
                continue
            article_id = str(article.get("id", ""))
            title = str(article.get("title", ""))
            url = str(article.get("url", ""))
            if article_id:
                result.append(Announcement(source, article_id, title, url))
        return result


def _is_listing_announcement(title: str) -> bool:
    title_lower = title.lower()
    return any(kw in title_lower for kw in _LISTING_KEYWORDS)


def format_announcement_message(ann: Announcement, lang: str = "ru") -> str:
    lines = [
        t("ann.header", lang, source=ann.source),
        f"<b>{ann.title}</b>",
    ]
    if ann.url:
        lines.append("\n" + t("ann.read_link", lang, url=ann.url))
    return "\n".join(lines)
