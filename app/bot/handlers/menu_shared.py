from __future__ import annotations

import re
from datetime import timedelta

from aiogram.fsm.state import State, StatesGroup

_TICKER_RE = re.compile(r"^[A-Z0-9]{1,16}$")
_DURATION_RE = re.compile(r"^(\d+)(m|h|d)$", re.IGNORECASE)
_ALERT_RE = re.compile(
    r"^([A-Z0-9]{1,16})\s*([><])\s*([\d.]+)(?:\s+(\w+))?$",
    re.IGNORECASE,
)

_KNOWN_EXCHANGES = {"binance", "bybit"}
_BAR_WIDTH = 10
_PAGE_SIZE = 10
_PERIODS = [
    ("24h", timedelta(hours=24)),
    ("7d", timedelta(days=7)),
    ("30d", timedelta(days=30)),
]
_MARKET_EMOJI = {"spot": "🟢", "futures": "🔵"}


class MenuFSM(StatesGroup):
    watch_add = State()
    watch_remove = State()
    alert_add = State()
    unalert = State()
    pause_set = State()

