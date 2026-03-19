from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.bot.handlers import start
from app.config import Settings


def _settings() -> Settings:
    return Settings(
        bot_token="token",
        database_url="sqlite+aiosqlite://",
        poll_interval_sec=60,
        dedup_ttl_hours=24,
        max_notifications_per_hour=20,
        min_vol_5m=10_000.0,
        max_spread=0.02,
        bootstrap_on_empty=True,
        default_only_usdt=False,
        default_min_score=10,
        default_enabled_exchanges=("binance", "bybit", "coinbase", "okx", "mexc"),
        default_enabled_market_types=("spot", "futures"),
        admin_id=None,
    )


class _SessionFactory:
    def __init__(self, *sessions: MagicMock) -> None:
        self._sessions = list(sessions) or [_session()]
        self._index = 0

    def __call__(self):  # noqa: ANN204
        if self._index < len(self._sessions):
            session = self._sessions[self._index]
        else:
            session = self._sessions[-1]
        self._index += 1

        class _Ctx:
            async def __aenter__(self_inner):  # noqa: ANN202
                return session

            async def __aexit__(self_inner, exc_type, exc, tb):  # noqa: ANN202
                return False

        return _Ctx()


def _session(*, existing_user: object | None) -> MagicMock:
    session = MagicMock()
    session.commit = AsyncMock()
    session.get = AsyncMock(return_value=existing_user)
    session.flush = AsyncMock()
    session.add = MagicMock()
    return session


def _message(*, user_id: int = 123, lang: str = "en", with_user: bool = True) -> SimpleNamespace:
    from_user = None if not with_user else SimpleNamespace(id=user_id, language_code=lang)
    return SimpleNamespace(text="/start", from_user=from_user, answer=AsyncMock())


def _callback(*, user_id: int = 123, lang: str = "en", with_message: bool = True) -> SimpleNamespace:
    message = None
    if with_message:
        message = SimpleNamespace(edit_text=AsyncMock(), answer=AsyncMock())
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id, language_code=lang),
        message=message,
        answer=AsyncMock(),
    )


def _user(settings: dict | None = None, user_id: int = 123) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, settings=settings or {})


@pytest.mark.asyncio
async def test_cmd_start_ignores_missing_user() -> None:
    message = _message(with_user=False)

    await start.cmd_start(message, _SessionFactory(_session(existing_user=None)), _settings())

    message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_start_for_new_user_starts_onboarding(monkeypatch: pytest.MonkeyPatch) -> None:
    message = _message()
    session = _session(existing_user=None)
    user = _user(
        {
            "lang": "en",
            "enabled_exchanges": ["binance", "bybit"],
            "enabled_market_types": ["spot", "futures"],
            "only_usdt": False,
            "min_score": 10,
        }
    )
    monkeypatch.setattr(
        "app.bot.handlers.start.users_repo.get_or_create_user",
        AsyncMock(return_value=user),
    )
    log_event = AsyncMock()
    monkeypatch.setattr("app.bot.handlers.start.analytics_repo.log_event", log_event)

    await start.cmd_start(message, _SessionFactory(session), _settings())

    assert message.answer.await_count == 2
    assert "Hello" in message.answer.await_args_list[0].args[0]
    assert "Step 1 of 3" in message.answer.await_args_list[1].args[0]
    assert log_event.await_count == 2
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_cmd_start_for_returning_user_shows_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    existing = _user(
        {
            "lang": "en",
            "enabled_exchanges": ["binance", "okx"],
            "enabled_market_types": ["spot"],
            "only_usdt": True,
            "min_score": 35,
            "digest_mode": True,
        }
    )
    session = _session(existing_user=existing)
    message = _message()
    monkeypatch.setattr(
        "app.bot.handlers.start.users_repo.get_or_create_user",
        AsyncMock(return_value=existing),
    )
    monkeypatch.setattr("app.bot.handlers.start.analytics_repo.log_event", AsyncMock())

    await start.cmd_start(message, _SessionFactory(session), _settings())

    text = message.answer.await_args.args[0]
    assert "Welcome back" in text
    assert "Binance, Okx" in text
    assert "Spot" in text
    assert "digest" in text.lower()


@pytest.mark.asyncio
async def test_cb_ob_exchange_requires_one_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    user = _user({"lang": "en", "enabled_exchanges": ["binance"]})
    monkeypatch.setattr(
        "app.bot.handlers.start.users_repo.get_or_create_user",
        AsyncMock(return_value=user),
    )
    callback = _callback()

    await start.cb_ob_exchange(
        callback,
        SimpleNamespace(exchange="binance"),
        _SessionFactory(_session(existing_user=None)),
        _settings(),
    )

    callback.answer.assert_awaited_once()
    assert "At least one exchange required" in callback.answer.await_args.args[0]
    assert callback.answer.await_args.kwargs["show_alert"] is True
    callback.message.edit_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_cb_ob_exchange_updates_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    user = _user({"lang": "en", "enabled_exchanges": ["binance", "bybit"]})
    session = _session(existing_user=None)
    monkeypatch.setattr(
        "app.bot.handlers.start.users_repo.get_or_create_user",
        AsyncMock(return_value=user),
    )
    callback = _callback()

    await start.cb_ob_exchange(
        callback,
        SimpleNamespace(exchange="okx"),
        _SessionFactory(session),
        _settings(),
    )

    assert set(user.settings["enabled_exchanges"]) == {"binance", "bybit", "okx"}
    callback.message.edit_text.assert_awaited_once()
    assert "Step 1 of 3" in callback.message.edit_text.await_args.args[0]
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_cb_ob_market_requires_one_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    user = _user({"lang": "en", "enabled_market_types": ["spot"]})
    monkeypatch.setattr(
        "app.bot.handlers.start.users_repo.get_or_create_user",
        AsyncMock(return_value=user),
    )
    callback = _callback()

    await start.cb_ob_market(
        callback,
        SimpleNamespace(market="spot"),
        _SessionFactory(_session(existing_user=None)),
        _settings(),
    )

    assert "At least one market type required" in callback.answer.await_args.args[0]
    assert callback.answer.await_args.kwargs["show_alert"] is True


@pytest.mark.asyncio
async def test_cb_ob_market_updates_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    user = _user({"lang": "en", "enabled_market_types": ["spot"]})
    session = _session(existing_user=None)
    monkeypatch.setattr(
        "app.bot.handlers.start.users_repo.get_or_create_user",
        AsyncMock(return_value=user),
    )
    callback = _callback()

    await start.cb_ob_market(
        callback,
        SimpleNamespace(market="futures"),
        _SessionFactory(session),
        _settings(),
    )

    assert set(user.settings["enabled_market_types"]) == {"spot", "futures"}
    callback.message.edit_text.assert_awaited_once()
    assert "Step 2 of 3" in callback.message.edit_text.await_args.args[0]


@pytest.mark.asyncio
async def test_cb_ob_next_moves_between_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    user = _user(
        {
            "lang": "en",
            "enabled_exchanges": ["binance"],
            "enabled_market_types": ["spot"],
        }
    )
    monkeypatch.setattr(
        "app.bot.handlers.start.users_repo.get_or_create_user",
        AsyncMock(return_value=user),
    )
    first = _callback()
    second = _callback()

    await start.cb_ob_next(
        first,
        SimpleNamespace(from_step=1),
        _SessionFactory(_session(existing_user=None)),
        _settings(),
    )
    await start.cb_ob_next(
        second,
        SimpleNamespace(from_step=2),
        _SessionFactory(_session(existing_user=None)),
        _settings(),
    )

    assert "Step 2 of 3" in first.message.edit_text.await_args.args[0]
    assert "Step 3 of 3" in second.message.edit_text.await_args.args[0]


@pytest.mark.asyncio
async def test_cb_ob_mode_saves_settings_and_finishes(monkeypatch: pytest.MonkeyPatch) -> None:
    user = _user(
        {
            "lang": "en",
            "enabled_exchanges": ["binance", "okx"],
            "enabled_market_types": ["spot", "futures"],
        }
    )
    session = _session(existing_user=None)
    monkeypatch.setattr(
        "app.bot.handlers.start.users_repo.get_or_create_user",
        AsyncMock(return_value=user),
    )
    callback = _callback()

    await start.cb_ob_mode(
        callback,
        SimpleNamespace(digest=1),
        _SessionFactory(session),
        _settings(),
    )

    assert user.settings["digest_mode"] is True
    callback.message.edit_text.assert_awaited_once()
    assert "Done" in callback.message.edit_text.await_args.args[0]
    callback.message.answer.assert_awaited_once()
    assert "Use the menu buttons" in callback.message.answer.await_args.args[0]
    callback.answer.assert_awaited_once()
    assert "saved" in callback.answer.await_args.args[0].lower()
