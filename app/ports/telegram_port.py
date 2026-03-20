from abc import ABC, abstractmethod


class TelegramControlPort(ABC):
    @abstractmethod
    async def send_message(self, text: str):
        pass

    @abstractmethod
    async def receive_commands(self):
        pass
