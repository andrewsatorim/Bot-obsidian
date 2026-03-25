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
from app.monitoring.health import HealthCheck
from app.monitoring.metrics import MetricsCollector
from app.risk.risk_manager import RiskManager
from app.strategy.breakout import BreakoutStrategy
from app.strategy.funding_mean_reversion import FundingMeanReversionStrategy
from app.strategy.fusion import StrategyFusion
from app.strategy.trend_following import TrendFollowingStrategy
from app.telegram.bot_adapter import TelegramBotAdapter

logger = logging.getLogger(__name__)

_shutdown = asyncio.Event()


def _handle_signal(*_: object) -> None:
    _shutdown.set()


def _build_strategy(symbol: str):
    """Build a fused strategy combining all sub-strategies."""
    funding = FundingMeanReversionStrategy(symbol=symbol)
    breakout = BreakoutStrategy(symbol=symbol)
    trend = TrendFollowingStrategy(symbol=symbol)
    return StrategyFusion(
        strategies=[(funding, 1.0), (breakout, 0.8), (trend, 0.7)],
        min_agreement=1,
        min_strength=0.3,
    )


async def run() -> None:
    settings = Settings()
    setup_logging(settings.log_level)

    # Monitoring
    metrics = MetricsCollector()
    health = HealthCheck(metrics, port=8080)

    # Data feed: live or simulated
    if settings.paper_trading:
        data_feed = SimulatedDataFeed()
        execution = PaperExecutor()
    else:
        from app.feeds.ccxt_feed import CcxtDataFeed
        from app.execution.ccxt_executor import CcxtExecutor
        data_feed = CcxtDataFeed(settings.exchange_id, settings.exchange_api_key, settings.exchange_api_secret, settings.exchange_passphrase)
        execution = CcxtExecutor(settings.exchange_id, settings.exchange_api_key, settings.exchange_api_secret, settings.exchange_passphrase)

    analytics = FeatureEngine()
    strategy = _build_strategy(settings.symbol)
    risk = RiskManager(settings)
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

    await health.start()
    await telegram.send_message(f"Bot-Obsidian started: {settings.symbol} (paper={settings.paper_trading})")

    metrics.set_equity(settings.account_equity)

    while not _shutdown.is_set():
        try:
            result = await orchestrator.step()

            # Update metrics
            state = orchestrator.state_machine.state
            metrics.set_engine_state(settings.symbol, state.value)
            if orchestrator._active_position:
                metrics.set_unrealized_pnl(settings.symbol, orchestrator._active_position.unrealized_pnl)
                metrics.set_open_positions(1)
            else:
                metrics.set_open_positions(0)

            if result:
                metrics.inc_trades(result.symbol, result.direction.value)
                msg = f"Trade: {result.direction.value} {result.symbol} @ {result.entry_price:.2f}"
                await telegram.send_message(msg)
        except Exception:
            logger.exception("unhandled error in main loop")
            metrics.inc_errors("main_loop")

        try:
            await asyncio.wait_for(_shutdown.wait(), timeout=settings.scan_interval_sec)
        except asyncio.TimeoutError:
            pass

    logger.info("Bot-Obsidian shutting down")
    await telegram.send_message("Bot-Obsidian stopped")
    await health.stop()

    # Cleanup live connections
    if hasattr(data_feed, "close"):
        await data_feed.close()
    if hasattr(execution, "close"):
        await execution.close()


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
