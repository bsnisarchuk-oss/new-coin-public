from __future__ import annotations


def calculate_score(
    exchange: str,
    quote: str,
    flags: list[str],
    enriched: dict | None = None,
) -> int:
    base = 0
    exchange_norm = exchange.lower()
    if exchange_norm == "binance":
        base += 35
    elif exchange_norm == "bybit":
        base += 30
    elif exchange_norm == "okx":
        base += 25
    elif exchange_norm == "mexc":
        base += 20
    elif exchange_norm == "coinbase":
        base += 20

    if quote.upper() in ("USDT", "USD"):
        base += 10
    if "LOW_LIQUIDITY" in flags:
        base -= 10
    if "HIGH_SPREAD" in flags:
        base -= 10

    # Volume bonus/penalty based on approximate 5-minute USDT-equivalent volume
    volume_5m = (enriched or {}).get("volume_5m")
    if volume_5m is not None:
        try:
            vol = float(volume_5m)
            if vol >= 100_000:
                base += 15
            elif vol >= 10_000:
                base += 5
            elif vol < 1_000:
                base -= 10
        except (TypeError, ValueError):
            pass

    return max(0, min(100, base))

