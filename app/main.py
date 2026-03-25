from __future__ import annotations

import asyncio
import logging
import signal
import sys

from app.analytics.feature_engine import FeatureEngine
from app.config import Settings
from app.core.orchestrator import Orchestrator
from app.execution.paper_executor import PaperExecutor
from app.feeds.simulated_feed import SimulatedDataFeed
from app.logging_config import setup_logging
from app.risk.risk_manager import RiskManager
from app.strategy.funding_mean_reversion import FundingMeanReversionStrategy
from app.telegram.bot_adapter import TelegramBotAdapter

logger = logging.getLogger(__name__)

_shutdown = asyncio.Event()


def _handle_signal(*_: object) -> None:
    _shutdown.set()


async def run() -> None:
    settings = Settings()
    setup_logging(settings.log_level)

    data_feed = SimulatedDataFeed()
    analytics = FeatureEngine()
    strategy = FundingMeanReversionStrategy(symbol=settings.symbol)
    risk = RiskManager(settings)
    execution = PaperExecutor()
    telegram = TelegramBotAdapter(settings.telegram_bot_token, settings.telegram_chat_id)

    orchestrator = Orchestrator(
        data_feed=data_feed,
        analytics=analytics,
        strategy=strategy,
        risk=risk,
        execution=execution,
        symbol=settings.symbol,
        settings=settings,
    )

    logger.info(
        "Bot-Obsidian starting: symbol=%s paper=%s interval=%.1fs",
        settings.symbol, settings.paper_trading, settings.scan_interval_sec,
    )

    await telegram.send_message(f"Bot-Obsidian started: {settings.symbol} (paper={settings.paper_trading})")

    while not _shutdown.is_set():
        try:
            result = await orchestrator.step()
            if result:
                msg = f"Trade: {result.direction.value} {result.symbol} @ {result.entry_price:.2f}"
                await telegram.send_message(msg)
        except Exception:
            logger.exception("unhandled error in main loop")

        try:
            await asyncio.wait_for(_shutdown.wait(), timeout=settings.scan_interval_sec)
        except asyncio.TimeoutError:
            pass

    logger.info("Bot-Obsidian shutting down")
    await telegram.send_message("Bot-Obsidian stopped")


def main() -> None:
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _handle_signal)

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
