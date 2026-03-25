from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Optional

from app.ports.telegram_port import TelegramControlPort

logger = logging.getLogger(__name__)


class TelegramBotAdapter(TelegramControlPort):
    """Basic Telegram adapter for notifications and commands.

    Requires python-telegram-bot. If bot token is not set, operates in
    silent mode (logs messages instead of sending).
    """

    def __init__(self, bot_token: str = "", chat_id: str = "") -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._bot: Optional[object] = None
        self._command_queue: asyncio.Queue[str] = asyncio.Queue()

    async def send_message(self, text: str) -> None:
        if not self._bot_token or not self._chat_id:
            logger.info("[telegram-silent] %s", text)
            return

        try:
            from telegram import Bot

            if self._bot is None:
                self._bot = Bot(token=self._bot_token)
            await self._bot.send_message(chat_id=self._chat_id, text=text)  # type: ignore[union-attr]
            logger.debug("telegram message sent to %s", self._chat_id)
        except Exception:
            logger.exception("failed to send telegram message")

    async def receive_commands(self) -> AsyncIterator[str]:
        while True:
            cmd = await self._command_queue.get()
            yield cmd

    async def push_command(self, command: str) -> None:
        await self._command_queue.put(command)
