from abc import ABC, abstractmethod


class OnChainPort(ABC):
    @abstractmethod
    async def get_snapshot(self, symbol: str):
        pass
