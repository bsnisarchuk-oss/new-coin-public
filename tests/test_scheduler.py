from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.jobs.scheduler import schedule_detector_job


class _Scheduler:
    def __init__(self) -> None:
        self.jobs: dict[str, object] = {}

    def add_job(self, func, **kwargs):  # noqa: ANN001, ANN204
        self.jobs[kwargs["id"]] = func


class _SessionFactory:
    def __init__(self, sessions: list[MagicMock]) -> None:
        self._sessions = sessions
        self._index = 0

    def __call__(self):  # noqa: ANN204
        session = self._sessions[self._index]
        self._index += 1

        class _Ctx:
            async def __aenter__(self_inner):  # noqa: ANN202
                return session

            async def __aexit__(self_inner, exc_type, exc, tb):  # noqa: ANN202
                return False

        return _Ctx()


@pytest.mark.asyncio
async def test_detector_job_processes_delistings_in_separate_phase() -> None:
    scheduler = _Scheduler()
    phase1 = MagicMock()
    phase1.commit = AsyncMock()
    phase2 = MagicMock()
    phase2.commit = AsyncMock()
    phase3 = MagicMock()
    phase3.commit = AsyncMock()

    event = SimpleNamespace(
        exchange="binance",
        market_type=SimpleNamespace(value="spot"),
    )
    delisting = SimpleNamespace(symbol_base="DOGE", symbol_quote="USDT")

    detector = MagicMock()
    detector.detect_new_events = AsyncMock(return_value=([event], [delisting]))
    notifier = MagicMock()
    notifier.process_events = AsyncMock()
    delisting_notifier = MagicMock()
    delisting_notifier.notify = AsyncMock()

    schedule_detector_job(
        scheduler=scheduler,
        session_factory=_SessionFactory([phase1, phase2, phase3]),
        detector=detector,
        notifier=notifier,
        delisting_notifier=delisting_notifier,
        interval_sec=60,
    )

    job = scheduler.jobs["detector_poll"]
    await job()  # type: ignore[misc]

    detector.detect_new_events.assert_awaited_once_with(phase1)
    notifier.process_events.assert_awaited_once_with(phase2, [event])
    delisting_notifier.notify.assert_awaited_once_with(phase3, [delisting])
    phase1.commit.assert_awaited_once()
    phase2.commit.assert_awaited_once()
    phase3.commit.assert_awaited_once()
