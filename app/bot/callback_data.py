from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class WatchCB(CallbackData, prefix="w"):
    ticker: str


class TrackCB(CallbackData, prefix="t"):
    event_id: str


class MuteTickerCB(CallbackData, prefix="mt"):
    ticker: str


class MuteExchangeCB(CallbackData, prefix="mx"):
    exchange: str


class HistoryPageCB(CallbackData, prefix="hp"):
    page: int
    exchange: str  # empty string means "all exchanges"


class FilterExchangeCB(CallbackData, prefix="fe"):
    exchange: str  # "binance", "bybit", etc.


class FilterMarketCB(CallbackData, prefix="fm"):
    market: str  # "spot", "futures"


class FilterOnlyUsdtCB(CallbackData, prefix="fu"):
    pass


class FilterScoreCB(CallbackData, prefix="fs"):
    delta: int  # +10 or -10; 0 = show hint


class FilterCloseCB(CallbackData, prefix="fc"):
    pass


# ─── Event notification actions ──────────────────────────────────────────────


class MuteMenuCB(CallbackData, prefix="mm"):
    """Open the mute submenu for a notification."""
    event_id: str


class MuteMenuBackCB(CallbackData, prefix="mmb"):
    """Return from mute submenu to main notification keyboard."""
    event_id: str


class SubMuteTickerCB(CallbackData, prefix="smt"):
    """Mute a ticker from within the mute submenu."""
    event_id: str
    ticker: str


class SubMuteExchangeCB(CallbackData, prefix="sme"):
    """Mute an exchange from within the mute submenu."""
    event_id: str
    exchange: str


class QuickAlertCB(CallbackData, prefix="qa"):
    """Start the quick price-alert flow for a listed coin."""
    event_id: str
    ticker: str
    exchange: str


# ─── Onboarding wizard ───────────────────────────────────────────────────────


class OBExchangeCB(CallbackData, prefix="obe"):
    exchange: str  # toggle exchange during onboarding step 1


class OBMarketCB(CallbackData, prefix="obm"):
    market: str  # toggle market type during onboarding step 2


class OBNextCB(CallbackData, prefix="obn"):
    from_step: int  # 1 → show step 2; 2 → show step 3


class OBModeCB(CallbackData, prefix="obd"):
    digest: int  # 0 = instant, 1 = digest-hourly


# ─── Main menu navigation ─────────────────────────────────────────────────────


class MenuActionCB(CallbackData, prefix="ma"):
    action: str  # watchlist, watch_add, watch_remove, alerts_list, alert_add,
    #              unalert, filters, presets, pause, digest_toggle,
    #              analytics, top, history, export, help, status,
    #              cancel_fsm, close
