from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class TelegramControlPort(ABC):
    @abstractmethod
    async def send_message(self, text: str) -> None:
        pass

    @abstractmethod
    async def receive_commands(self) -> AsyncIterator[str]:
        pass
