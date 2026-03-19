from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.announcements import Announcement, AnnouncementMonitor


class _SessionFactory:
    def __call__(self):  # noqa: ANN204
        session = MagicMock()
        session.commit = AsyncMock()

        class _Ctx:
            async def __aenter__(self_inner):  # noqa: ANN202
                return session

            async def __aexit__(self_inner, exc_type, exc, tb):  # noqa: ANN202
                return False

        return _Ctx()


@pytest.mark.asyncio
async def test_announcement_monitor_persists_seen_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    storage: dict[str, object] = {}

    async def fake_get_payload(session, service, state_key):  # noqa: ANN001, ANN202
        return dict(storage) if storage else None

    async def fake_set_payload(session, service, state_key, payload):  # noqa: ANN001, ANN202
        storage.clear()
        storage.update(payload)

    first = Announcement("Binance", "1", "Binance will list ABC", "")
    second = Announcement("Binance", "2", "Binance will list XYZ", "")

    monitor = AnnouncementMonitor(session_factory=_SessionFactory())
    monkeypatch.setattr("app.services.announcements.state_repo.get_payload", fake_get_payload)
    monkeypatch.setattr("app.services.announcements.state_repo.set_payload", fake_set_payload)

    monitor._fetch = AsyncMock(return_value=[first])  # type: ignore[method-assign]
    assert await monitor.check_new() == []
    assert storage["initialized"] is True
    assert storage["seen_ids"] == ["1"]

    monitor._fetch = AsyncMock(return_value=[first, second])  # type: ignore[method-assign]
    items = await monitor.check_new()
    assert [item.article_id for item in items] == ["2"]
    assert storage["seen_ids"] == ["1", "2"]
