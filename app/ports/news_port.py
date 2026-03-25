from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.event import Event


class NewsPort(ABC):
    @abstractmethod
    async def get_events(self) -> list[Event]:
        pass
