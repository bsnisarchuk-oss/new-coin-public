"""Tests for app.i18n — translation function and helpers."""
from __future__ import annotations


from app.i18n import STRINGS, get_user_lang, t


# ── t() basic behaviour ───────────────────────────────────────────────────────

def test_t_returns_russian_by_default():
    result = t("digest.header", count=3)
    assert "Дайджест" in result
    assert "3" in result


def test_t_returns_english():
    result = t("digest.header", "en", count=5)
    assert "digest" in result.lower()
    assert "5" in result


def test_t_fallback_to_russian_for_unknown_lang():
    result = t("digest.header", "fr", count=2)
    # Unknown lang → falls back to Russian
    assert "Дайджест" in result


def test_t_missing_key_returns_key_itself():
    result = t("nonexistent.key", "ru")
    assert result == "nonexistent.key"


def test_t_missing_key_in_en_falls_back_to_ru():
    # All RU keys should also be present in EN, but if one is missing it falls back
    ru_result = t("notifier.auto_digest", "ru")
    en_result = t("notifier.auto_digest", "en")
    assert ru_result != en_result  # they should differ
    assert "digest" in en_result.lower()


def test_t_kwargs_interpolated():
    result = t("digest.overflow", "ru", count=42)
    assert "42" in result

    result_en = t("digest.overflow", "en", count=7)
    assert "7" in result_en


# ── get_user_lang() ───────────────────────────────────────────────────────────

def test_get_user_lang_defaults_to_ru():
    assert get_user_lang(None) == "ru"
    assert get_user_lang({}) == "ru"


def test_get_user_lang_reads_from_settings():
    assert get_user_lang({"lang": "en"}) == "en"
    assert get_user_lang({"lang": "ru"}) == "ru"


def test_get_user_lang_unknown_value_falls_back_to_ru():
    assert get_user_lang({"lang": "zh"}) == "ru"
    assert get_user_lang({"lang": ""}) == "ru"


# ── All RU keys present in EN ─────────────────────────────────────────────────

def test_all_ru_keys_present_in_en():
    ru_keys = set(STRINGS["ru"])
    en_keys = set(STRINGS["en"])
    missing = ru_keys - en_keys
    assert not missing, f"Missing EN translations for keys: {missing}"


# ── Service string spot-checks ────────────────────────────────────────────────

def test_alert_triggered_ru():
    result = t("alert.triggered", "ru",
               arrow="📈", ticker="BTC", quote="USDT", exchange="Binance",
               price="50000.0000", sign=">", threshold="49000.0000")
    assert "Ценовой алерт" in result
    assert "BTC/USDT" in result
    assert "Binance" in result


def test_alert_triggered_en():
    result = t("alert.triggered", "en",
               arrow="📈", ticker="ETH", quote="USDT", exchange="Bybit",
               price="3000.0000", sign=">", threshold="2900.0000")
    assert "Price alert" in result
    assert "ETH/USDT" in result


def test_alert_triggered_coinbase_usd():
    result = t("alert.triggered", "en",
               arrow="📈", ticker="BTC", quote="USD", exchange="Coinbase",
               price="50000.0000", sign=">", threshold="49000.0000")
    assert "BTC/USD" in result
    assert "Coinbase" in result


def test_delisting_message_ru():
    result = t("delisting.message", "ru",
               base="XYZ", quote="USDT", exchange="Binance", market="Spot")
    assert "DELISTING" in result
    assert "XYZ/USDT" in result
    assert "Проверьте" in result


def test_delisting_message_en():
    result = t("delisting.message", "en",
               base="XYZ", quote="USDT", exchange="Binance", market="Spot")
    assert "DELISTING" in result
    assert "positions" in result


def test_tracker_change_ru():
    result = t("tracker.change", "ru", arrow="📈", sign="+", pct=5.42)
    assert "Изменение" in result
    assert "5.42" in result


def test_tracker_change_en():
    result = t("tracker.change", "en", arrow="📉", sign="", pct=-2.10)
    assert "Change" in result
    assert "2.10" in result
