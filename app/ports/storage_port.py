from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class StoragePort(ABC):
    @abstractmethod
    async def save(self, key: str, data: Any) -> None:
        pass

    @abstractmethod
    async def load(self, key: str) -> Optional[Any]:
        pass
