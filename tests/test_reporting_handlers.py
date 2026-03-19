from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import BufferedInputFile

from app.bot.handlers import channel, export, history, status, top
from app.config import Settings
from app.db.models import EventType, MarketType


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
    session.execute = AsyncMock()
    return session


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


def _callback(*, user_id: int = 123, lang: str = "en", with_message: bool = True) -> SimpleNamespace:
    message = None
    if with_message:
        message = SimpleNamespace(edit_text=AsyncMock(), answer=AsyncMock())
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id, language_code=lang),
        message=message,
        answer=AsyncMock(),
    )


def _user(*, settings: dict | None = None, user_id: int = 123) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, settings=settings or {})


def _event(
    base: str = "BTC",
    *,
    quote: str = "USDT",
    exchange: str = "binance",
    market: MarketType = MarketType.SPOT,
    score: int = 42,
    price: str | None = "50000",
    first_seen_at: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        exchange=exchange,
        event_type=EventType.SPOT_LISTING,
        market_type=market,
        symbol_base=base,
        symbol_quote=quote,
        first_seen_at=first_seen_at or datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
        enriched={"price": price} if price else {},
        score=score,
        flags=["hot"],
    )


@pytest.mark.asyncio
async def test_channel_handlers_cover_usage_errors_and_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.bot.handlers.channel.get_or_create_user",
        AsyncMock(side_effect=[_user(), _user(), _user(), _user(), _user(settings={"linked_channel_id": -1001})]),
    )

    usage_message = _message("/setchannel")
    await channel.cmd_setchannel(
        usage_message,
        SimpleNamespace(send_message=AsyncMock(), delete_message=AsyncMock()),
        _SessionFactory(_session()),
        _settings(),
    )
    assert "Usage: <code>/setchannel" in usage_message.answer.await_args.args[0]

    invalid_message = _message("/setchannel abc")
    await channel.cmd_setchannel(
        invalid_message,
        SimpleNamespace(send_message=AsyncMock(), delete_message=AsyncMock()),
        _SessionFactory(_session()),
        _settings(),
    )
    assert "Channel ID must be a number" in invalid_message.answer.await_args.args[0]

    forbidden_message = _message("/setchannel -1001")
    forbidden_bot = SimpleNamespace(
        send_message=AsyncMock(side_effect=TelegramForbiddenError(MagicMock(), "forbidden")),
        delete_message=AsyncMock(),
    )
    await channel.cmd_setchannel(forbidden_message, forbidden_bot, _SessionFactory(_session()), _settings())
    assert "not an admin" in forbidden_message.answer.await_args.args[0]

    bad_request_message = _message("/setchannel -1002")
    bad_request_bot = SimpleNamespace(
        send_message=AsyncMock(side_effect=TelegramBadRequest(MagicMock(), "chat not found")),
        delete_message=AsyncMock(),
    )
    await channel.cmd_setchannel(
        bad_request_message,
        bad_request_bot,
        _SessionFactory(_session()),
        _settings(),
    )
    assert "chat not found" in bad_request_message.answer.await_args.args[0]

    first_session = _session()
    second_session = _session()
    user = _user(settings={})
    monkeypatch.setattr(
        "app.bot.handlers.channel.get_or_create_user",
        AsyncMock(side_effect=[user, user]),
    )
    success_message = _message("/setchannel -1003")
    bot = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=99)),
        delete_message=AsyncMock(),
    )
    await channel.cmd_setchannel(
        success_message,
        bot,
        _SessionFactory(first_session, second_session),
        _settings(),
    )
    bot.send_message.assert_awaited_once()
    bot.delete_message.assert_awaited_once_with(-1003, 99)
    assert user.settings["linked_channel_id"] == -1003
    assert "Channel <code>-1003</code> linked" in success_message.answer.await_args.args[0]

    unset_user = _user(settings={"linked_channel_id": -1003})
    monkeypatch.setattr(
        "app.bot.handlers.channel.get_or_create_user",
        AsyncMock(return_value=unset_user),
    )
    unset_message = _message("/unsetchannel")
    await channel.cmd_unsetchannel(unset_message, _SessionFactory(_session()), _settings())
    assert "linked_channel_id" not in unset_user.settings
    assert "Channel unlinked" in unset_message.answer.await_args.args[0]


def test_history_helpers_render_pages_and_navigation() -> None:
    event = _event()
    text = history._format_history_page(
        [event],
        page=1,
        total=25,
        exchange_filter="binance",
        lang="en",
    )
    keyboard = history._build_nav_keyboard(page=1, total=25, exchange_filter="binance", lang="en")

    assert "Listing history [Binance]" in text
    assert "page 2/3" in text
    assert "BTC/USDT" in text
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert labels == ["\u25c0 Prev", "Next \u25b6"]


@pytest.mark.asyncio
async def test_cmd_history_handles_invalid_exchange_and_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    user = _user()
    monkeypatch.setattr(
        "app.bot.handlers.history.users_repo.get_or_create_user",
        AsyncMock(return_value=user),
    )

    invalid_message = _message("/history kraken")
    await history.cmd_history(
        invalid_message,
        SimpleNamespace(args="kraken"),
        _SessionFactory(_session()),
        _settings(),
    )
    assert "Invalid exchange" in invalid_message.answer.await_args.args[0]

    valid_message = _message("/history binance")
    monkeypatch.setattr(
        "app.bot.handlers.history.events_repo.list_events_page",
        AsyncMock(return_value=([_event()], 1)),
    )
    await history.cmd_history(
        valid_message,
        SimpleNamespace(args="binance"),
        _SessionFactory(_session()),
        _settings(),
    )
    text = valid_message.answer.await_args.args[0]
    assert "Listing history [Binance]" in text
    assert "BTC/USDT" in text
    keyboard = valid_message.answer.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard == []


@pytest.mark.asyncio
async def test_history_callback_updates_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.bot.handlers.history.users_repo.get_or_create_user",
        AsyncMock(return_value=_user()),
    )
    monkeypatch.setattr(
        "app.bot.handlers.history.events_repo.list_events_page",
        AsyncMock(return_value=([_event("ETH", exchange="bybit", score=50)], 12)),
    )
    callback = _callback()

    await history.cb_history_page(
        callback,
        SimpleNamespace(page=1, exchange="bybit"),
        _SessionFactory(_session()),
        _settings(),
    )

    callback.message.edit_text.assert_awaited_once()
    assert "ETH/USDT" in callback.message.edit_text.await_args.args[0]
    callback.answer.assert_awaited_once()


def test_pause_status_formats_active_invalid_and_missing() -> None:
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    assert status._pause_status({}, "en") == "none"
    assert status._pause_status({"paused_until": "bad"}, "en") == "none"
    assert status._pause_status({"paused_until": future}, "en").startswith("until ")


@pytest.mark.asyncio
async def test_cmd_status_builds_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    message = _message("/status")
    user = _user(settings={"digest_mode": True})
    monkeypatch.setattr(
        "app.bot.handlers.status.users_repo.get_or_create_user",
        AsyncMock(return_value=user),
    )
    monkeypatch.setattr(
        "app.bot.handlers.status.watchlist_repo.list_watchlist",
        AsyncMock(return_value=["BTC"]),
    )
    monkeypatch.setattr(
        "app.bot.handlers.status.mutes_repo.list_mutes",
        AsyncMock(return_value=["mute"]),
    )
    monkeypatch.setattr(
        "app.bot.handlers.status.alerts_repo.list_active_alerts",
        AsyncMock(return_value=[1, 2]),
    )
    monkeypatch.setattr(
        "app.bot.handlers.status.events_repo.count_events_last_hours",
        AsyncMock(return_value=7),
    )

    await status.cmd_status(message, _SessionFactory(_session()), _settings())

    text = message.answer.await_args.args[0]
    assert "<b>Bot status</b>" in text
    assert "Events over 24h: 7" in text
    assert "Digest: on" in text
    assert "<b>Alerts:</b> 2 active" in text


@pytest.mark.asyncio
async def test_cmd_top_handles_empty_and_populated_results(monkeypatch: pytest.MonkeyPatch) -> None:
    empty_message = _message("/top")
    session = _session()
    session.execute = AsyncMock(return_value=SimpleNamespace(scalars=lambda: []))
    monkeypatch.setattr(
        "app.bot.handlers.top.users_repo.get_or_create_user",
        AsyncMock(return_value=_user()),
    )
    await top.cmd_top(empty_message, _SessionFactory(session), _settings())
    assert "No new listings were detected" in empty_message.answer.await_args.args[0]

    full_message = _message("/top")
    session = _session()
    session.execute = AsyncMock(return_value=SimpleNamespace(scalars=lambda: [_event(), _event("ETH", price=None)]))
    monkeypatch.setattr(
        "app.bot.handlers.top.users_repo.get_or_create_user",
        AsyncMock(return_value=_user()),
    )
    await top.cmd_top(full_message, _SessionFactory(session), _settings())
    text = full_message.answer.await_args.args[0]
    assert "Top listings over 24 hours" in text
    assert "BTC/USDT" in text
    assert "ETH/USDT" in text


@pytest.mark.asyncio
async def test_cmd_export_handles_empty_and_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    empty_message = _message("/export")
    session = _session()
    session.execute = AsyncMock(return_value=SimpleNamespace(scalars=lambda: []))
    monkeypatch.setattr(
        "app.bot.handlers.export.users_repo.get_or_create_user",
        AsyncMock(return_value=_user()),
    )
    await export.cmd_export(empty_message, _SessionFactory(session), _settings())
    assert "No listings found over the last 7 days." in empty_message.answer.await_args.args[0]

    full_message = _message("/export")
    session = _session()
    session.execute = AsyncMock(return_value=SimpleNamespace(scalars=lambda: [_event(), _event("ETH", exchange="okx")]))
    monkeypatch.setattr(
        "app.bot.handlers.export.users_repo.get_or_create_user",
        AsyncMock(return_value=_user()),
    )
    await export.cmd_export(full_message, _SessionFactory(session), _settings())

    document = full_message.answer_document.await_args.args[0]
    assert isinstance(document, BufferedInputFile)
    assert document.filename.startswith("listings_")
    csv_body = document.data.decode("utf-8-sig")
    assert "date_utc,exchange,market_type,event_type,base,quote,score,flags,price,volume_5m" in csv_body
    assert "binance" in csv_body
    assert "okx" in csv_body
    caption = full_message.answer_document.await_args.kwargs["caption"]
    assert "Listings from the last 7 days" in caption
    assert "2 rows" in caption
