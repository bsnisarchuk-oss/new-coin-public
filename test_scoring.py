from app.services.scoring import calculate_score


# ─── Binance ───────────────────────────────────────────────────────────────────

def test_score_binance_usdt_clean() -> None:
    assert calculate_score("binance", "USDT", []) == 45  # 35 + 10


def test_score_binance_non_usdt() -> None:
    assert calculate_score("binance", "BTC", []) == 35


def test_score_binance_with_penalties() -> None:
    assert calculate_score("binance", "USDT", ["LOW_LIQUIDITY", "HIGH_SPREAD"]) == 25  # 45 - 20


# ─── Bybit ─────────────────────────────────────────────────────────────────────

def test_score_bybit_usdt_clean() -> None:
    assert calculate_score("bybit", "USDT", []) == 40  # 30 + 10


def test_score_bybit_with_penalties() -> None:
    assert calculate_score("bybit", "BTC", ["LOW_LIQUIDITY", "HIGH_SPREAD"]) == 10  # 30 - 20


# ─── OKX ───────────────────────────────────────────────────────────────────────

def test_score_okx_usdt_clean() -> None:
    assert calculate_score("okx", "USDT", []) == 35  # 25 + 10


def test_score_okx_non_usdt() -> None:
    assert calculate_score("okx", "BTC", []) == 25


def test_score_okx_with_penalty() -> None:
    assert calculate_score("okx", "USDT", ["HIGH_SPREAD"]) == 25  # 35 - 10


# ─── MEXC ──────────────────────────────────────────────────────────────────────

def test_score_mexc_usdt_clean() -> None:
    assert calculate_score("mexc", "USDT", []) == 30  # 20 + 10


def test_score_mexc_all_penalties() -> None:
    # 20 - 20 = 0, clamp to 0
    assert calculate_score("mexc", "BTC", ["LOW_LIQUIDITY", "HIGH_SPREAD"]) == 0


# ─── Coinbase ──────────────────────────────────────────────────────────────────

def test_score_coinbase_usdt_clean() -> None:
    assert calculate_score("coinbase", "USDT", []) == 30  # 20 + 10


def test_score_coinbase_usd_pair() -> None:
    # Coinbase uses USD — treated equivalent to USDT, gets +10 bonus
    assert calculate_score("coinbase", "USD", []) == 30  # 20 + 10


# ─── Unknown exchange ──────────────────────────────────────────────────────────

def test_score_unknown_exchange_with_usdt() -> None:
    assert calculate_score("kraken", "USDT", []) == 10  # 0 + 10


def test_score_unknown_exchange_no_bonus() -> None:
    assert calculate_score("kraken", "EUR", []) == 0


# ─── Clamping ──────────────────────────────────────────────────────────────────

def test_score_never_negative() -> None:
    assert calculate_score("kraken", "BTC", ["LOW_LIQUIDITY", "HIGH_SPREAD"]) == 0


def test_score_never_above_100() -> None:
    assert calculate_score("binance", "USDT", []) <= 100


# ─── Case insensitivity ────────────────────────────────────────────────────────

def test_score_exchange_case_insensitive() -> None:
    assert calculate_score("Binance", "USDT", []) == calculate_score("binance", "USDT", [])
    assert calculate_score("OKX", "USDT", []) == calculate_score("okx", "USDT", [])
    assert calculate_score("MEXC", "USDT", []) == calculate_score("mexc", "USDT", [])


# ─── Volume bonus ───────────────────────────────────────────────────────────────

def test_score_volume_high_bonus() -> None:
    # vol >= 100_000 → +15
    score = calculate_score("binance", "USDT", [], enriched={"volume_5m": 200_000})
    assert score == 60  # 35 + 10 + 15

def test_score_volume_medium_bonus() -> None:
    # vol >= 10_000 → +5
    score = calculate_score("binance", "USDT", [], enriched={"volume_5m": 50_000})
    assert score == 50  # 35 + 10 + 5

def test_score_volume_low_penalty() -> None:
    # vol < 1_000 → -10
    score = calculate_score("binance", "USDT", [], enriched={"volume_5m": 500})
    assert score == 35  # 35 + 10 - 10

def test_score_volume_none_no_effect() -> None:
    # no volume data → same as without enriched
    score_with = calculate_score("binance", "USDT", [], enriched={"volume_5m": None})
    score_without = calculate_score("binance", "USDT", [])
    assert score_with == score_without == 45
