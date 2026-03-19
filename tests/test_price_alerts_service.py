from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.price_alerts import PriceAlertService


class _SessionFactory:
    def __init__(self, session: MagicMock) -> None:
        self._session = session

    def __call__(self):  # noqa: ANN204
        class _Ctx:
            async def __aenter__(self_inner):  # noqa: ANN202
                return self._session

            async def __aexit__(self_inner, exc_type, exc, tb):  # noqa: ANN202
                return False

        return _Ctx()


def _alert() -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        user_id=123,
        ticker="BTC",
        exchange="binance",
        direction="gt",
        threshold=Decimal("90"),
    )


@pytest.mark.asyncio
async def test_alert_marked_triggered_only_after_success(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock()
    session.get = AsyncMock(return_value=SimpleNamespace(settings={"lang": "ru"}))
    session.commit = AsyncMock()

    service = PriceAlertService(
        bot=SimpleNamespace(send_message=AsyncMock()),
        session_factory=_SessionFactory(session),
        enrichment_service=MagicMock(),
    )
    service._fetch_price = AsyncMock(return_value=Decimal("100"))  # type: ignore[method-assign]
    service._send = AsyncMock(return_value=True)  # type: ignore[method-assign]

    list_alerts = AsyncMock(return_value=[_alert()])
    mark_triggered = AsyncMock()
    monkeypatch.setattr("app.services.price_alerts.alerts_repo.list_all_active_alerts", list_alerts)
    monkeypatch.setattr("app.services.price_alerts.alerts_repo.mark_triggered", mark_triggered)

    await service.check_all()

    mark_triggered.assert_awaited_once_with(session, 1)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_alert_not_marked_when_send_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock()
    session.get = AsyncMock(return_value=SimpleNamespace(settings={"lang": "ru"}))
    session.commit = AsyncMock()

    service = PriceAlertService(
        bot=SimpleNamespace(send_message=AsyncMock()),
        session_factory=_SessionFactory(session),
        enrichment_service=MagicMock(),
    )
    service._fetch_price = AsyncMock(return_value=Decimal("100"))  # type: ignore[method-assign]
    service._send = AsyncMock(return_value=False)  # type: ignore[method-assign]

    list_alerts = AsyncMock(return_value=[_alert()])
    mark_triggered = AsyncMock()
    monkeypatch.setattr("app.services.price_alerts.alerts_repo.list_all_active_alerts", list_alerts)
    monkeypatch.setattr("app.services.price_alerts.alerts_repo.mark_triggered", mark_triggered)

    await service.check_all()

    mark_triggered.assert_not_awaited()
    session.commit.assert_awaited_once()
