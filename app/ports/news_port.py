from abc import ABC, abstractmethod


class NewsPort(ABC):
    @abstractmethod
    async def get_events(self):
        pass
