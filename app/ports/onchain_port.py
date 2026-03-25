from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.onchain_snapshot import OnChainSnapshot


class OnChainPort(ABC):
    @abstractmethod
    async def get_snapshot(self, symbol: str) -> OnChainSnapshot:
        pass
