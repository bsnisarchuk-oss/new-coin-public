from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.db.models import Event, EventType, MarketType
from app.services.digest import DigestService


class _SessionFactory:
    def __init__(self, sessions: list[MagicMock]) -> None:
        self._sessions = sessions
        self._index = 0

    def __call__(self):  # noqa: ANN204
        if self._index >= len(self._sessions):
            raise AssertionError("SessionFactory called more times than expected")
        session = self._sessions[self._index]
        self._index += 1

        class _Ctx:
            async def __aenter__(self_inner):  # noqa: ANN202
                return session

            async def __aexit__(self_inner, exc_type, exc, tb):  # noqa: ANN202
                return False

        return _Ctx()


def _event() -> Event:
    return Event(
        id=uuid4(),
        exchange="binance",
        event_type=EventType.SPOT_LISTING,
        market_type=MarketType.SPOT,
        symbol_base="BTC",
        symbol_quote="USDT",
        first_seen_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
        event_key="binance:SPOT_LISTING:spot:BTC:USDT",
        pairs=["BTCUSDT"],
        meta={},
        enriched={},
        score=42,
        flags=[],
    )


@pytest.mark.asyncio
async def test_digest_deletes_queue_only_after_success(monkeypatch: pytest.MonkeyPatch) -> None:
    ev = _event()
    user_id = 42

    s1 = MagicMock()
    s2 = MagicMock()
    s2.get = AsyncMock(return_value=SimpleNamespace(settings={"lang": "ru"}))
    s3 = MagicMock()
    s3.commit = AsyncMock()
    service = DigestService(
        bot=SimpleNamespace(send_message=AsyncMock()),
        session_factory=_SessionFactory([s1, s2, s3]),
    )

    list_users = AsyncMock(return_value=[user_id])
    list_items = AsyncMock(return_value=[(ev.id, ev)])
    delete_items = AsyncMock()
    monkeypatch.setattr("app.services.digest.digest_repo.list_users_with_queue", list_users)
    monkeypatch.setattr("app.services.digest.digest_repo.list_user_queue_items", list_items)
    monkeypatch.setattr("app.services.digest.digest_repo.delete_user_queue_items", delete_items)

    await service.send_pending_digests()

    delete_items.assert_awaited_once_with(s3, user_id, [ev.id])
    s3.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_digest_keeps_queue_on_send_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    ev = _event()
    user_id = 7

    failing_bot = SimpleNamespace(send_message=AsyncMock(side_effect=Exception("network")))
    s1 = MagicMock()
    s2 = MagicMock()
    s2.get = AsyncMock(return_value=SimpleNamespace(settings={"lang": "ru"}))
    service = DigestService(
        bot=failing_bot,
        session_factory=_SessionFactory([s1, s2]),
    )

    list_users = AsyncMock(return_value=[user_id])
    list_items = AsyncMock(return_value=[(ev.id, ev)])
    delete_items = AsyncMock()
    monkeypatch.setattr("app.services.digest.digest_repo.list_users_with_queue", list_users)
    monkeypatch.setattr("app.services.digest.digest_repo.list_user_queue_items", list_items)
    monkeypatch.setattr("app.services.digest.digest_repo.delete_user_queue_items", delete_items)

    await service.send_pending_digests()

    delete_items.assert_not_awaited()
