from abc import ABC, abstractmethod


class DataFeedPort(ABC):
    @abstractmethod
    async def get_market_data(self, symbol: str):
        pass
