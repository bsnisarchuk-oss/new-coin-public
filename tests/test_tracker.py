"""Tests for tracker sparkline and format function (pure, no I/O)."""
from __future__ import annotations

from app.services.tracker import _format_tracking_report, sparkline


# ── sparkline() ───────────────────────────────────────────────────────────────

def test_sparkline_empty_returns_empty():
    assert sparkline([]) == ""


def test_sparkline_single_value_returns_middle_block():
    result = sparkline([100.0])
    assert result == "▄"  # middle of 8 blocks (index 3.5 → 4, but round(3.5)=4 → "▅")
    # actually let's just assert length and valid chars
    assert len(result) == 1
    assert result in "▁▂▃▄▅▆▇█"


def test_sparkline_all_same_values():
    result = sparkline([50.0, 50.0, 50.0])
    assert len(result) == 3
    # all same → all middle block
    assert len(set(result)) == 1


def test_sparkline_ascending_series():
    result = sparkline([1.0, 2.0, 3.0, 4.0, 5.0])
    assert len(result) == 5
    # First char should be lowest block (▁), last should be highest (█)
    assert result[0] == "▁"
    assert result[-1] == "█"
    # Should be monotonically non-decreasing
    for i in range(len(result) - 1):
        assert result[i] <= result[i + 1]


def test_sparkline_descending_series():
    result = sparkline([5.0, 4.0, 3.0, 2.0, 1.0])
    assert result[0] == "█"
    assert result[-1] == "▁"


def test_sparkline_length_matches_input():
    prices = [1.0, 3.0, 2.0, 5.0, 4.0, 2.5, 1.5]
    result = sparkline(prices)
    assert len(result) == 7


def test_sparkline_only_valid_block_chars():
    prices = [10.5, 20.3, 15.0, 8.2, 25.1, 12.0]
    result = sparkline(prices)
    for ch in result:
        assert ch in "▁▂▃▄▅▆▇█"


# ── _format_tracking_report() ─────────────────────────────────────────────────

def _base_kwargs(**overrides) -> dict:
    kw = dict(
        exchange="binance",
        base="BTC",
        quote="USDT",
        minutes=15,
        enriched={"price": 50000.0, "volume_5m": 1000.0, "spread": 0.001},
        flags=[],
        initial_price=48000.0,
        klines=None,
        lang="ru",
    )
    kw.update(overrides)
    return kw


def test_format_report_contains_header():
    text = _format_tracking_report(**_base_kwargs())
    assert "TRACK 15m" in text
    assert "BTC/USDT" in text
    assert "Binance" in text


def test_format_report_shows_price_change():
    text = _format_tracking_report(**_base_kwargs(initial_price=48000.0))
    assert "+" in text or "%" in text


def test_format_report_no_chart_when_klines_none():
    text = _format_tracking_report(**_base_kwargs(klines=None))
    assert "📊" not in text


def test_format_report_no_chart_when_klines_empty():
    text = _format_tracking_report(**_base_kwargs(klines=[]))
    assert "📊" not in text


def test_format_report_chart_shown_with_klines():
    prices = [48000.0, 48500.0, 49000.0, 49500.0, 50000.0]
    text = _format_tracking_report(**_base_kwargs(klines=prices))
    assert "📊" in text
    assert "▁" in text or "█" in text  # sparkline chars present
    assert "1m×5" in text


def test_format_report_chart_label_5m_for_60m():
    prices = [100.0] * 12
    text = _format_tracking_report(**_base_kwargs(minutes=60, klines=prices))
    assert "5m×12" in text


def test_format_report_english():
    text = _format_tracking_report(**_base_kwargs(lang="en"))
    assert "Change" in text


def test_format_report_flags_shown():
    text = _format_tracking_report(**_base_kwargs(flags=["LOW_LIQUIDITY"]))
    assert "LOW_LIQUIDITY" in text


def test_format_report_no_metrics_fallback():
    text = _format_tracking_report(**_base_kwargs(enriched={}, initial_price=None))
    assert "n/a" in text


def test_format_report_window_label_4h():
    text = _format_tracking_report(**_base_kwargs(minutes=240))
    assert "TRACK 4h" in text


def test_format_report_window_label_24h():
    text = _format_tracking_report(**_base_kwargs(minutes=1440))
    assert "TRACK 1d" in text


def test_format_report_chart_label_5m_for_240m():
    prices = [100.0] * 48
    text = _format_tracking_report(**_base_kwargs(minutes=240, klines=prices))
    assert "5m×48" in text


def test_format_report_chart_label_30m_for_1440m():
    prices = [100.0] * 48
    text = _format_tracking_report(**_base_kwargs(minutes=1440, klines=prices))
    assert "30m×48" in text
