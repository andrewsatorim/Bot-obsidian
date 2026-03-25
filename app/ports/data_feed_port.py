from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.market_data_bundle import MarketDataBundle


class DataFeedPort(ABC):
    @abstractmethod
    async def get_market_data(self, symbol: str) -> MarketDataBundle:
        pass
