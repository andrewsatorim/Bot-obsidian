from abc import ABC, abstractmethod


class StoragePort(ABC):
    @abstractmethod
    async def save(self, key: str, data):
        pass

    @abstractmethod
    async def load(self, key: str):
        pass
