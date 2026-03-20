from abc import ABC, abstractmethod


class ExchangePort(ABC):
    @abstractmethod
    async def place_order(self, order):
        pass

    @abstractmethod
    async def get_position(self, symbol: str):
        pass
