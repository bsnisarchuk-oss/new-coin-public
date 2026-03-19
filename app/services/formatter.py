"""Message formatting for listing event notifications.

Pure functions — no I/O, no DB, no Telegram calls.
Import here when you only need formatting, not delivery.
"""
from __future__ import annotations

from app.db.models import Event
from app.i18n import t


def format_event_message(event: Event, lang: str = "ru") -> str:
    first_seen = event.first_seen_at.strftime("%Y-%m-%d %H:%M")
    flags_text = ", ".join(event.flags) if event.flags else "-"
    enriched = event.enriched or {}

    # Primary exchange metrics
    metrics = []
    price = enriched.get("price")
    volume_5m = enriched.get("volume_5m")
    spread = enriched.get("spread")
    if price is not None:
        metrics.append(f"Price: {fmt_price(float(price))}")
    if volume_5m is not None:
        metrics.append(f"Vol(5m): {fmt_price(float(volume_5m))}")
    if spread is not None:
        metrics.append(f"Spread: {round(float(spread) * 100, 4)}%")
    metrics_text = " | ".join(metrics) if metrics else t("fmt.metrics_na", lang)

    event_type_text = event.event_type.value.replace("_", " ")
    header = (
        f"🆕 {event_type_text}: "
        f"{event.symbol_base}/{event.symbol_quote} — {event.exchange.capitalize()}"
    )
    body = (
        f"{header}\n"
        f"{t('fmt.first_seen', lang, dt=first_seen)}\n"
        f"{t('fmt.score_flags', lang, score=event.score, flags=flags_text)}\n"
        f"{metrics_text}"
    )

    # Cross-exchange arbitrage block
    arb_prices: dict = enriched.get("arb_prices") or {}
    arb_spread_pct = enriched.get("arb_spread_pct")
    cheapest = enriched.get("arb_cheapest")
    most_expensive = enriched.get("arb_most_expensive")

    if len(arb_prices) >= 2:
        lines = [t("fmt.arb_header", lang)]
        for exch, p in sorted(arb_prices.items()):
            mark = ""
            if exch == cheapest and cheapest != most_expensive:
                mark = " ↓"
            elif exch == most_expensive and cheapest != most_expensive:
                mark = " ↑"
            lines.append(f"  • {exch.capitalize()}: {fmt_price(p)}{mark}")
        if arb_spread_pct is not None and cheapest and most_expensive and cheapest != most_expensive:
            lines.append(
                t("fmt.arb_spread", lang,
                  pct=arb_spread_pct,
                  cheapest=cheapest.capitalize(),
                  most_expensive=most_expensive.capitalize())
            )
        body += "\n" + "\n".join(lines)

    # Coin info block (CoinGecko)
    coin_info: dict = enriched.get("coin_info") or {}
    if coin_info:
        lines = [t("fmt.coin_header", lang)]
        if coin_info.get("genesis_year"):
            lines.append(t("fmt.coin_genesis", lang, year=coin_info["genesis_year"]))
        if coin_info.get("description"):
            lines.append(f"  {coin_info['description']}")
        if coin_info.get("homepage"):
            lines.append(f"  🌐 {coin_info['homepage']}")
        body += "\n" + "\n".join(lines)

    return body


def fmt_price(value: float) -> str:
    """Format price: no trailing zeros, up to 8 significant digits."""
    if value >= 1000:
        return f"{value:,.2f}"
    if value >= 1:
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return f"{value:.8f}".rstrip("0").rstrip(".")


def extract_symbol(event: Event) -> str:
    if event.pairs and isinstance(event.pairs, list) and event.pairs:
        return str(event.pairs[0]).upper()
    return f"{event.symbol_base}{event.symbol_quote}".upper()
