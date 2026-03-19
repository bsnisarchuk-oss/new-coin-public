from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class Instrument:
    exchange: str
    market_type: str
    symbol: str
    base: str
    quote: str
    raw: dict[str, Any]


class ExchangeConnector(ABC):
    name: str
    supported_market_types: tuple[str, ...]

    @abstractmethod
    async def fetch_instruments(self, market_type: str) -> list[Instrument]:
        raise NotImplementedError

