"""The ONLY output channel of the signal engine: a Telegram text message.

This notifier is intentionally self-contained — it does NOT import
``app.telegram`` or any port/adapter from the main package, so the private
engine stays removable in one ``rm -rf`` and shares no code path with the
sellable bot. It can only *send text*; there is no order, position, or
execution concept anywhere in this module.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class TelegramSignalNotifier:
    """Send plain-text signal messages to a private Telegram chat.

    If no token/chat is configured the notifier runs in silent mode and just
    logs the message, which keeps tests and local dry-runs side-effect free.
    """

    def __init__(self, bot_token: str = "", chat_id: str = "") -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._bot: object | None = None

    async def send(self, text: str) -> None:
        if not self._bot_token or not self._chat_id:
            logger.info("[signal-telegram-silent] %s", text)
            return

        try:
            from telegram import Bot

            if self._bot is None:
                self._bot = Bot(token=self._bot_token)
            await self._bot.send_message(chat_id=self._chat_id, text=text)  # type: ignore[union-attr]
            logger.debug("signal message sent to %s", self._chat_id)
        except Exception:
            logger.exception("failed to send signal telegram message")
