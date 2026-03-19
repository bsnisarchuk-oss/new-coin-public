from __future__ import annotations

from urllib.parse import quote as url_quote

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callback_data import (
    MuteMenuBackCB,
    MuteMenuCB,
    QuickAlertCB,
    SubMuteExchangeCB,
    SubMuteTickerCB,
    TrackCB,
    WatchCB,
)
from app.db.models import Event, MarketType


def _label(key: str, lang: str, **kwargs: str) -> str:
    ru = {
        "watch": "➕ В избранное",
        "track": "📈 Отслеживать",
        "alert": "🔔 Алерт",
        "mute": "🔕 Скрыть ▾",
        "chart.exchange": "📊 {exchange} ↗",
        "chart.tradingview": "📊 TradingView ↗",
        "chart.tradingview_alt": "📈 TradingView ↗",
        "coingecko": "🦎 CoinGecko ↗",
        "mute.ticker": "🔕 Скрыть {ticker}",
        "mute.exchange": "🔕 Скрыть {exchange}",
        "back": "← Назад",
    }
    en = {
        "watch": "➕ Watch",
        "track": "📈 Track",
        "alert": "🔔 Alert",
        "mute": "🔕 Mute ▾",
        "chart.exchange": "📊 {exchange} ↗",
        "chart.tradingview": "📊 TradingView ↗",
        "chart.tradingview_alt": "📈 TradingView ↗",
        "coingecko": "🦎 CoinGecko ↗",
        "mute.ticker": "🔕 Mute {ticker}",
        "mute.exchange": "🔕 Mute {exchange}",
        "back": "← Back",
    }
    text = (en if lang == "en" else ru)[key]
    return text.format(**kwargs) if kwargs else text


def _build_exchange_url(
    exchange: str,
    market_type: MarketType,
    base: str,
    quote: str,
) -> str | None:
    """Return a direct trading-pair URL for the given exchange, or None if unknown."""
    b = base.upper()
    q = quote.upper()
    ex = exchange.lower()

    if ex == "binance":
        if market_type == MarketType.SPOT:
            return f"https://www.binance.com/en/trade/{b}_{q}"
        return f"https://www.binance.com/en/futures/{b}{q}"

    if ex == "bybit":
        if market_type == MarketType.SPOT:
            return f"https://www.bybit.com/en/trade/spot/{b}/{q}"
        return f"https://www.bybit.com/en/trade/usdt/{b}"

    if ex == "coinbase":
        return f"https://www.coinbase.com/advanced-trade/spot/{b}-{q}"

    if ex == "okx":
        if market_type == MarketType.SPOT:
            return f"https://www.okx.com/trade-spot/{b.lower()}-{q.lower()}"
        return f"https://www.okx.com/trade-perpetual/{b.lower()}-{q.lower()}-swap"

    if ex == "mexc":
        if market_type == MarketType.SPOT:
            return f"https://www.mexc.com/exchange/{b}_{q}"
        return f"https://futures.mexc.com/exchange/{b}_{q}"

    return None


def _build_tradingview_url(
    exchange: str,
    market_type: MarketType,
    base: str,
    quote: str,
) -> str:
    """Return a TradingView chart URL for the pair."""
    ex = exchange.lower()
    b = base.upper()
    q = quote.upper()

    if market_type == MarketType.FUTURES:
        # TradingView perpetual format differs by exchange.
        tv_perp = {
            "binance": f"BINANCE:{b}{q}.P",
            "bybit": f"BYBIT:{b}{q}.P",
            "okx": f"OKX:{b}{q}.P",
            "mexc": f"MEXC:{b}{q}.P",
            "coinbase": f"COINBASE:{b}{q}.P",
        }
        symbol = tv_perp.get(ex, f"{ex.upper()}:{b}{q}.P")
    else:
        tv_spot = {
            "binance": "BINANCE",
            "bybit": "BYBIT",
            "okx": "OKX",
            "mexc": "MEXC",
            "coinbase": "COINBASE",
        }
        tv_exchange = tv_spot.get(ex, ex.upper())
        symbol = f"{tv_exchange}:{b}{q}"

    return f"https://www.tradingview.com/chart/?symbol={url_quote(symbol, safe='')}"


def build_event_actions(event: Event, lang: str = "ru") -> InlineKeyboardMarkup:
    """Main inline keyboard attached to every listing notification."""
    base = event.symbol_base.upper()[:16]
    quote = event.symbol_quote.upper()[:16]
    exchange = event.exchange.lower()[:16]
    event_id = str(event.id)

    rows = [
        [
            InlineKeyboardButton(
                text=_label("watch", lang),
                callback_data=WatchCB(ticker=base).pack(),
            ),
            InlineKeyboardButton(
                text=_label("track", lang),
                callback_data=TrackCB(event_id=event_id).pack(),
            ),
        ],
        [
            InlineKeyboardButton(
                text=_label("alert", lang),
                callback_data=QuickAlertCB(
                    event_id=event_id,
                    ticker=base,
                    exchange=exchange,
                ).pack(),
            ),
            InlineKeyboardButton(
                text=_label("mute", lang),
                callback_data=MuteMenuCB(event_id=event_id).pack(),
            ),
        ],
    ]

    exchange_url = _build_exchange_url(exchange, event.market_type, base, quote)
    tv_url = _build_tradingview_url(exchange, event.market_type, base, quote)
    cg_url = f"https://www.coingecko.com/en/search?query={url_quote(base)}"

    chart_url = exchange_url or tv_url
    chart_label = (
        _label("chart.exchange", lang, exchange=event.exchange.capitalize())
        if exchange_url
        else _label("chart.tradingview", lang)
    )

    link_row = [InlineKeyboardButton(text=chart_label, url=chart_url)]
    if exchange_url:
        link_row.append(
            InlineKeyboardButton(
                text=_label("chart.tradingview_alt", lang),
                url=tv_url,
            )
        )
    rows.append(link_row)
    rows.append(
        [
            InlineKeyboardButton(
                text=_label("coingecko", lang),
                url=cg_url,
            ),
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_mute_submenu(event: Event, lang: str = "ru") -> InlineKeyboardMarkup:
    """Mute sub-menu shown when user taps the mute button."""
    base = event.symbol_base.upper()[:16]
    exchange = event.exchange.lower()[:16]
    event_id = str(event.id)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_label("mute.ticker", lang, ticker=base),
                    callback_data=SubMuteTickerCB(event_id=event_id, ticker=base).pack(),
                ),
                InlineKeyboardButton(
                    text=_label(
                        "mute.exchange",
                        lang,
                        exchange=event.exchange.capitalize(),
                    ),
                    callback_data=SubMuteExchangeCB(
                        event_id=event_id,
                        exchange=exchange,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=_label("back", lang),
                    callback_data=MuteMenuBackCB(event_id=event_id).pack(),
                ),
            ],
        ]
    )
