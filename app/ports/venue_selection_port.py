from abc import ABC, abstractmethod


class VenueSelectionPort(ABC):
    @abstractmethod
    async def select_venue(self, symbol: str, size: float):
        pass
