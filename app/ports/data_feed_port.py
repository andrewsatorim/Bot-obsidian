from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.market_bundle import MarketBundle


class DataFeedPort(ABC):
    @abstractmethod
    async def get_market_data(self, symbol: str) -> MarketBundle:
        """Return a market data bundle for the given symbol.

        Adapters must always populate `market`. All other fields are optional
        and default to empty collections / zero when not available.
        """
