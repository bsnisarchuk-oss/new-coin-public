from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.bot.keyboards.event_actions import build_event_actions
from app.bot.keyboards.filters_menu import build_filters_keyboard, render_filters_text
from app.bot.keyboards.main_menu import build_main_reply_keyboard
from app.bot.keyboards.onboarding import render_step1_text
from app.db.models import Event, EventType, MarketType
from app.services.filtering import UserFilters


def _event() -> Event:
    return Event(
        id=uuid4(),
        exchange="binance",
        event_type=EventType.SPOT_LISTING,
        market_type=MarketType.SPOT,
        symbol_base="AAA",
        symbol_quote="USDT",
        first_seen_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
        event_key="binance:SPOT_LISTING:spot:AAA:USDT",
        pairs=["AAAUSDT"],
        meta={},
        enriched={},
        score=42,
        flags=[],
    )


def _filters() -> UserFilters:
    return UserFilters(
        enabled_exchanges={"binance", "okx"},
        enabled_market_types={"spot"},
        only_usdt=True,
        min_score=30,
    )


def test_main_menu_keyboard_is_localized_for_english() -> None:
    keyboard = build_main_reply_keyboard("en")
    labels = [button.text for row in keyboard.keyboard for button in row]
    assert "👁 Watch" in labels
    assert "ℹ️ Help" in labels


def test_onboarding_step_text_is_localized_for_english() -> None:
    assert "Step 1 of 3" in render_step1_text("en")


def test_event_actions_keyboard_is_localized_for_english() -> None:
    keyboard = build_event_actions(_event(), "en")
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert "➕ Watch" in labels
    assert "🔕 Mute ▾" in labels


def test_filters_menu_is_localized_for_english() -> None:
    text = render_filters_text(_filters(), "en")
    keyboard = build_filters_keyboard(_filters(), "en")
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert "Notification filters" in text
    assert "USDT only: ✅" in labels
    assert "❌ Close" in labels
