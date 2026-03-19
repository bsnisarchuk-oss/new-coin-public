from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.bot import lang as bot_lang
from app.config import _as_bool, _as_float, _as_int, load_settings
from app.db.models import User
from app.db.repo import users as users_repo


def test_config_parsers_cover_common_inputs() -> None:
    assert _as_bool("true", False) is True
    assert _as_bool("0", True) is False
    assert _as_int("15", 1) == 15
    assert _as_float("2.5", 1.0) == 2.5


def test_load_settings_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BOT_TOKEN", raising=False)

    with pytest.raises(ValueError, match="BOT_TOKEN is required"):
        load_settings()


def test_load_settings_reads_defaults_and_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "abc")
    monkeypatch.setenv("ADMIN_ID", "42")
    monkeypatch.setenv("DEFAULT_ENABLED_EXCHANGES", "binance, okx")
    monkeypatch.setenv("DEFAULT_ENABLED_MARKET_TYPES", "spot")
    monkeypatch.setenv("DEFAULT_ONLY_USDT", "yes")
    monkeypatch.setenv("DEFAULT_MIN_SCORE", "25")

    settings = load_settings()

    assert settings.bot_token == "abc"
    assert settings.admin_id == 42
    assert settings.default_enabled_exchanges == ("binance", "okx")
    assert settings.default_enabled_market_types == ("spot",)
    assert settings.default_only_usdt is True
    assert settings.default_min_score == 25
    assert settings.database_url.endswith("@postgres:5432/new_coin_bot")


@pytest.mark.asyncio
async def test_get_or_create_user_returns_existing_with_default_settings() -> None:
    user = SimpleNamespace(id=123, settings={})
    session = MagicMock()
    session.get = AsyncMock(return_value=user)

    created = await users_repo.get_or_create_user(
        session,
        123,
        SimpleNamespace(
            default_enabled_exchanges=("binance", "okx"),
            default_enabled_market_types=("spot",),
            default_only_usdt=True,
            default_min_score=35,
        ),
    )

    assert created is user
    assert created.settings["enabled_exchanges"] == ["binance", "okx"]
    assert created.settings["enabled_market_types"] == ["spot"]
    assert created.settings["only_usdt"] is True
    assert created.settings["min_score"] == 35


@pytest.mark.asyncio
async def test_get_or_create_user_creates_new_record() -> None:
    session = MagicMock()
    session.get = AsyncMock(return_value=None)
    session.flush = AsyncMock()
    session.add = MagicMock()
    settings = SimpleNamespace(
        default_enabled_exchanges=("binance", "okx"),
        default_enabled_market_types=("spot", "futures"),
        default_only_usdt=False,
        default_min_score=10,
    )

    user = await users_repo.get_or_create_user(session, 777, settings)

    assert isinstance(user, User)
    assert user.id == 777
    session.add.assert_called_once_with(user)
    session.flush.assert_awaited_once()


def test_users_repo_helpers_and_language_selection() -> None:
    merged = users_repo.merge_user_settings({"lang": "ru", "foo": 1}, {"lang": "en", "bar": 2})
    assert merged == {"lang": "en", "foo": 1, "bar": 2}

    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    user = SimpleNamespace(settings={"digest_only_until": future, "paused_until": future})
    expired_user = SimpleNamespace(settings={"digest_only_until": past, "paused_until": "bad"})
    assert users_repo.is_user_in_digest_mode(user) is True
    assert users_repo.is_user_paused(user) is True
    assert users_repo.is_user_in_digest_mode(expired_user) is False
    assert users_repo.is_user_paused(expired_user) is False

    assert bot_lang.guess_lang("en-GB") == "en"
    assert bot_lang.guess_lang("ru") == "ru"
    assert bot_lang.preferred_lang({"lang": "en"}, telegram_lang_code="ru") == "en"
    assert bot_lang.preferred_lang({}, telegram_lang_code="en-US") == "en"
