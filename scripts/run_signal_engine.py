"""Entrypoint for the PRIVATE signal engine — runs as a SEPARATE process.

This script is the only place the private engine is launched. It loads its own
config from ``.env.signal`` (separate Telegram token), builds the engine, and
runs it. It imports ONLY ``app.signal_engine.*`` — never the executor,
orchestrator or any execution port.

Run:
    python scripts/run_signal_engine.py

Remove the entire private engine with:
    rm -rf app/signal_engine scripts/run_signal_engine.py
"""

from __future__ import annotations

import asyncio
import logging

from app.feeds.ccxt_feed import CcxtDataFeed
from app.signal_engine.config import SignalSettings
from app.signal_engine.engine import SignalEngine
from app.signal_engine.notifier import TelegramSignalNotifier


async def _main() -> None:
    settings = SignalSettings()
    logging.basicConfig(level=settings.log_level)

    # Read-only market data source. CcxtDataFeed is wired HERE (in the script),
    # not inside the package, so app.signal_engine stays import-light and the
    # whole engine remains removable with one rm -rf.
    data_source = CcxtDataFeed(exchange_id="okx")

    notifier = TelegramSignalNotifier(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )
    engine = SignalEngine(
        settings=settings,
        notifier=notifier,
        data_source=data_source,
    )

    try:
        await engine.run_forever()
    finally:
        await data_source.close()


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
