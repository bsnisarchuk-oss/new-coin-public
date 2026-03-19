from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.bot.handlers import alert, digest, help as help_handler, lang as lang_handler, pause, watchlist
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
        default_min_score=0,
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


def _session() -> MagicMock:
    session = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    return session


def _user(*, settings: dict | None = None, user_id: int = 123) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, settings=settings or {})


def _message(
    text: str,
    *,
    user_id: int = 123,
    lang: str = "en",
    with_user: bool = True,
) -> SimpleNamespace:
    from_user = None if not with_user else SimpleNamespace(id=user_id, language_code=lang)
    return SimpleNamespace(
        text=text,
        from_user=from_user,
        answer=AsyncMock(),
        answer_document=AsyncMock(),
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("btc", "BTC"),
        ("ETH123", "ETH123"),
        ("a_b", None),
        ("", None),
        ("a" * 17, None),
    ],
)
def test_watchlist_validate_ticker(raw: str, expected: str | None) -> None:
    assert watchlist._validate_ticker(raw) == expected


@pytest.mark.asyncio
async def test_cmd_watch_rejects_invalid_ticker(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session()
    message = _message("/watch ???")
    monkeypatch.setattr(
        "app.bot.handlers.watchlist.users_repo.get_or_create_user",
        AsyncMock(return_value=_user()),
    )

    await watchlist.cmd_watch(
        message,
        SimpleNamespace(args="???"),
        _SessionFactory(session),
        _settings(),
    )

    session.commit.assert_awaited_once()
    message.answer.assert_awaited_once()
    assert "Format: /watch" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_cmd_watch_adds_ticker(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session()
    message = _message("/watch btc")
    monkeypatch.setattr(
        "app.bot.handlers.watchlist.users_repo.get_or_create_user",
        AsyncMock(return_value=_user()),
    )
    add_watch = AsyncMock(return_value=True)
    monkeypatch.setattr("app.bot.handlers.watchlist.watchlist_repo.add_watch", add_watch)

    await watchlist.cmd_watch(
        message,
        SimpleNamespace(args="btc"),
        _SessionFactory(session),
        _settings(),
    )

    add_watch.assert_awaited_once_with(session, 123, "BTC")
    assert "BTC added to the watchlist" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_cmd_watch_reports_duplicate(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session()
    message = _message("/watch btc")
    monkeypatch.setattr(
        "app.bot.handlers.watchlist.users_repo.get_or_create_user",
        AsyncMock(return_value=_user()),
    )
    monkeypatch.setattr(
        "app.bot.handlers.watchlist.watchlist_repo.add_watch",
        AsyncMock(return_value=False),
    )

    await watchlist.cmd_watch(
        message,
        SimpleNamespace(args="btc"),
        _SessionFactory(session),
        _settings(),
    )

    text = message.answer.await_args.args[0]
    assert "BTC is already in the watchlist" in text
    assert str(watchlist.watchlist_repo._MAX_WATCHLIST_SIZE) in text


@pytest.mark.asyncio
async def test_cmd_watchlist_renders_items(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session()
    message = _message("/watchlist")
    monkeypatch.setattr(
        "app.bot.handlers.watchlist.users_repo.get_or_create_user",
        AsyncMock(return_value=_user()),
    )
    monkeypatch.setattr(
        "app.bot.handlers.watchlist.watchlist_repo.list_watchlist",
        AsyncMock(return_value=["BTC", "ETH"]),
    )

    await watchlist.cmd_watchlist(message, _SessionFactory(session), _settings())

    assert message.answer.await_args.args[0] == "Watchlist: BTC, ETH"


@pytest.mark.asyncio
async def test_cmd_watchlist_renders_empty_state(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session()
    message = _message("/watchlist")
    monkeypatch.setattr(
        "app.bot.handlers.watchlist.users_repo.get_or_create_user",
        AsyncMock(return_value=_user()),
    )
    monkeypatch.setattr(
        "app.bot.handlers.watchlist.watchlist_repo.list_watchlist",
        AsyncMock(return_value=[]),
    )

    await watchlist.cmd_watchlist(message, _SessionFactory(session), _settings())

    assert message.answer.await_args.args[0] == "Watchlist: -"


@pytest.mark.asyncio
async def test_cmd_unwatch_handles_invalid_and_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session()
    invalid_message = _message("/unwatch ???")
    missing_message = _message("/unwatch btc")
    monkeypatch.setattr(
        "app.bot.handlers.watchlist.users_repo.get_or_create_user",
        AsyncMock(return_value=_user()),
    )
    remove_watch = AsyncMock(return_value=False)
    monkeypatch.setattr("app.bot.handlers.watchlist.watchlist_repo.remove_watch", remove_watch)

    await watchlist.cmd_unwatch(
        invalid_message,
        SimpleNamespace(args="???"),
        _SessionFactory(session),
        _settings(),
    )
    await watchlist.cmd_unwatch(
        missing_message,
        SimpleNamespace(args="btc"),
        _SessionFactory(_session()),
        _settings(),
    )

    assert "Format: /unwatch" in invalid_message.answer.await_args.args[0]
    remove_watch.assert_awaited_once()
    assert missing_message.answer.await_args.args[0] == "BTC was not found in the watchlist"


@pytest.mark.asyncio
async def test_cmd_unwatch_removes_ticker(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session()
    message = _message("/unwatch btc")
    monkeypatch.setattr(
        "app.bot.handlers.watchlist.users_repo.get_or_create_user",
        AsyncMock(return_value=_user()),
    )
    monkeypatch.setattr(
        "app.bot.handlers.watchlist.watchlist_repo.remove_watch",
        AsyncMock(return_value=True),
    )

    await watchlist.cmd_unwatch(
        message,
        SimpleNamespace(args="btc"),
        _SessionFactory(session),
        _settings(),
    )

    assert message.answer.await_args.args[0] == "BTC removed from the watchlist"


@pytest.mark.asyncio
async def test_cmd_alert_shows_help_when_args_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session()
    message = _message("/alert")
    monkeypatch.setattr(
        "app.bot.handlers.alert.users_repo.get_or_create_user",
        AsyncMock(return_value=_user()),
    )

    await alert.cmd_alert(
        message,
        SimpleNamespace(args=None),
        _SessionFactory(session),
        _settings(),
    )

    text = message.answer.await_args.args[0]
    assert "Format: /alert" in text
    assert "/unalert <ID>" in text


@pytest.mark.asyncio
async def test_cmd_alert_rejects_invalid_price_and_unknown_exchange(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.bot.handlers.alert.users_repo.get_or_create_user",
        AsyncMock(return_value=_user()),
    )

    invalid_price_message = _message("/alert BTC > 1.2.3")
    await alert.cmd_alert(
        invalid_price_message,
        SimpleNamespace(args="BTC > 1.2.3"),
        _SessionFactory(_session()),
        _settings(),
    )
    assert invalid_price_message.answer.await_args.args[0] == "Invalid price value."

    unknown_exchange_message = _message("/alert BTC > 10 kraken")
    await alert.cmd_alert(
        unknown_exchange_message,
        SimpleNamespace(args="BTC > 10 kraken"),
        _SessionFactory(_session()),
        _settings(),
    )
    assert "Unknown exchange: kraken" in unknown_exchange_message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_cmd_alert_creates_alert(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session()
    message = _message("/alert BTC > 50000 bybit")
    monkeypatch.setattr(
        "app.bot.handlers.alert.users_repo.get_or_create_user",
        AsyncMock(return_value=_user()),
    )
    create_alert = AsyncMock(return_value=SimpleNamespace(id=77))
    monkeypatch.setattr("app.bot.handlers.alert.alerts_repo.create_alert", create_alert)

    await alert.cmd_alert(
        message,
        SimpleNamespace(args="BTC > 50000 bybit"),
        _SessionFactory(session),
        _settings(),
    )

    create_alert.assert_awaited_once_with(
        session=session,
        user_id=123,
        ticker="BTC",
        direction="gt",
        threshold=Decimal("50000"),
        exchange="bybit",
    )
    text = message.answer.await_args.args[0]
    assert "Alert created [ID 77]" in text
    assert "BTC/USDT > 50000 on Bybit" in text


@pytest.mark.asyncio
async def test_cmd_alert_respects_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    message = _message("/alert BTC > 10")
    monkeypatch.setattr(
        "app.bot.handlers.alert.users_repo.get_or_create_user",
        AsyncMock(return_value=_user()),
    )
    monkeypatch.setattr(
        "app.bot.handlers.alert.alerts_repo.create_alert",
        AsyncMock(return_value=None),
    )

    await alert.cmd_alert(
        message,
        SimpleNamespace(args="BTC > 10"),
        _SessionFactory(_session()),
        _settings(),
    )

    assert "Alert limit reached" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_cmd_alerts_lists_active_alerts(monkeypatch: pytest.MonkeyPatch) -> None:
    message = _message("/alerts")
    monkeypatch.setattr(
        "app.bot.handlers.alert.users_repo.get_or_create_user",
        AsyncMock(return_value=_user()),
    )
    monkeypatch.setattr(
        "app.bot.handlers.alert.alerts_repo.list_active_alerts",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    id=1,
                    ticker="BTC",
                    direction="gt",
                    threshold=Decimal("50000"),
                    exchange="binance",
                ),
                SimpleNamespace(
                    id=2,
                    ticker="ETH",
                    direction="lt",
                    threshold=Decimal("2000"),
                    exchange=None,
                ),
            ]
        ),
    )

    await alert.cmd_alerts(message, _SessionFactory(_session()), _settings())

    text = message.answer.await_args.args[0]
    assert "<b>Active alerts:</b>" in text
    assert "[1] BTC/USDT > 50000" in text
    assert "[2] ETH/USDT < 2000" in text


@pytest.mark.asyncio
async def test_cmd_alerts_empty_and_unalert_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    empty_message = _message("/alerts")
    delete_message = _message("/unalert 1")
    invalid_message = _message("/unalert bad")
    monkeypatch.setattr(
        "app.bot.handlers.alert.users_repo.get_or_create_user",
        AsyncMock(return_value=_user()),
    )
    monkeypatch.setattr(
        "app.bot.handlers.alert.alerts_repo.list_active_alerts",
        AsyncMock(return_value=[]),
    )
    deactivate = AsyncMock(return_value=True)
    monkeypatch.setattr("app.bot.handlers.alert.alerts_repo.deactivate_alert", deactivate)

    await alert.cmd_alerts(empty_message, _SessionFactory(_session()), _settings())
    await alert.cmd_unalert(
        invalid_message,
        SimpleNamespace(args="bad"),
        _SessionFactory(_session()),
        _settings(),
    )
    await alert.cmd_unalert(
        delete_message,
        SimpleNamespace(args="1"),
        _SessionFactory(_session()),
        _settings(),
    )

    assert empty_message.answer.await_args.args[0] == "No active alerts. Create one with /alert BTC > 50000"
    assert "Format: /unalert <ID>" in invalid_message.answer.await_args.args[0]
    deactivate.assert_awaited_once()
    assert deactivate.await_args.args[1:] == (123, 1)
    assert delete_message.answer.await_args.args[0] == "Alert [1] deleted."


@pytest.mark.asyncio
async def test_cmd_digest_usage_status_and_toggle(monkeypatch: pytest.MonkeyPatch) -> None:
    invalid_message = _message("/digest maybe")
    status_message = _message("/digest")
    enable_message = _message("/digest on")
    disable_message = _message("/digest off")
    current_off_user = _user(settings={})
    current_on_user = _user(settings={"digest_mode": True})
    monkeypatch.setattr(
        "app.bot.handlers.digest.users_repo.get_or_create_user",
        AsyncMock(side_effect=[current_off_user, current_off_user, current_off_user, current_on_user]),
    )

    await digest.cmd_digest(
        invalid_message,
        SimpleNamespace(args="maybe"),
        _SessionFactory(_session()),
        _settings(),
    )
    await digest.cmd_digest(
        status_message,
        SimpleNamespace(args=""),
        _SessionFactory(_session()),
        _settings(),
    )
    await digest.cmd_digest(
        enable_message,
        SimpleNamespace(args="on"),
        _SessionFactory(_session()),
        _settings(),
    )
    await digest.cmd_digest(
        disable_message,
        SimpleNamespace(args="off"),
        _SessionFactory(_session()),
        _settings(),
    )

    assert invalid_message.answer.await_args.args[0] == "Usage: /digest on  or  /digest off"
    assert "Digest mode is currently <b>disabled</b>." in status_message.answer.await_args.args[0]
    assert current_off_user.settings["digest_mode"] is True
    assert "Digest mode enabled" in enable_message.answer.await_args.args[0]
    assert current_on_user.settings["digest_mode"] is False
    assert "Digest mode disabled" in disable_message.answer.await_args.args[0]


def test_parse_pause_duration() -> None:
    assert pause._parse_duration("30m") == timedelta(minutes=30)
    assert pause._parse_duration("2h") == timedelta(hours=2)
    assert pause._parse_duration("1d") == timedelta(days=1)
    assert pause._parse_duration("bad") is None


@pytest.mark.asyncio
async def test_cmd_pause_handles_none_remove_invalid_and_clamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    no_pause_message = _message("/pause")
    remove_message = _message("/pause")
    invalid_message = _message("/pause no")
    clamp_message = _message("/pause 10d")
    active_pause = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=1)
    no_pause_user = _user(settings={})
    remove_user = _user(settings={"paused_until": active_pause.isoformat()})
    clamp_user = _user(settings={})
    monkeypatch.setattr(
        "app.bot.handlers.pause.users_repo.get_or_create_user",
        AsyncMock(side_effect=[no_pause_user, remove_user, _user(settings={}), clamp_user]),
    )

    await pause.cmd_pause(
        no_pause_message,
        SimpleNamespace(args=""),
        _SessionFactory(_session()),
        _settings(),
    )
    await pause.cmd_pause(
        remove_message,
        SimpleNamespace(args=""),
        _SessionFactory(_session()),
        _settings(),
    )
    await pause.cmd_pause(
        invalid_message,
        SimpleNamespace(args="no"),
        _SessionFactory(_session()),
        _settings(),
    )
    await pause.cmd_pause(
        clamp_message,
        SimpleNamespace(args="10d"),
        _SessionFactory(_session()),
        _settings(),
    )

    assert no_pause_message.answer.await_args.args[0] == "Notifications are active, there is no pause."
    assert remove_user.settings["paused_until"] is None
    assert remove_message.answer.await_args.args[0] == "Pause removed. Notifications resumed."
    assert "Invalid format" in invalid_message.answer.await_args.args[0]
    paused_until = datetime.fromisoformat(clamp_user.settings["paused_until"])
    assert paused_until - datetime.now(timezone.utc) <= timedelta(hours=72, seconds=5)
    assert "Notifications paused until" in clamp_message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_cmd_help_and_lang(monkeypatch: pytest.MonkeyPatch) -> None:
    help_message = _message("/help")
    current_message = _message("/lang")
    invalid_message = _message("/lang de")
    change_message = _message("/lang en")
    user = _user(settings={"lang": "en"})
    monkeypatch.setattr(
        "app.bot.handlers.help.users_repo.get_or_create_user",
        AsyncMock(return_value=user),
    )
    monkeypatch.setattr(
        "app.bot.handlers.lang.users_repo.get_or_create_user",
        AsyncMock(return_value=user),
    )

    await help_handler.cmd_help(help_message, _SessionFactory(_session()), _settings())
    await lang_handler.cmd_lang(current_message, _SessionFactory(_session()), _settings())
    await lang_handler.cmd_lang(invalid_message, _SessionFactory(_session()), _settings())
    await lang_handler.cmd_lang(change_message, _SessionFactory(_session()), _settings())

    assert "/status" in help_message.answer.await_args.args[0]
    assert "Current language: <b>en</b>" in current_message.answer.await_args.args[0]
    assert "Unknown language" in invalid_message.answer.await_args.args[0]
    assert user.settings["lang"] == "en"
    assert "Language changed to English" in change_message.answer.await_args.args[0]
