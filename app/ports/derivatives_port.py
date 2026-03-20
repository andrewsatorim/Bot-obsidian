from abc import ABC, abstractmethod


class DerivativesPort(ABC):
    @abstractmethod
    async def get_oi(self, symbol: str):
        pass

    @abstractmethod
    async def get_funding(self, symbol: str):
        pass
