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

import ccxt.async_support as ccxt_async

from app.feeds.ccxt_feed import CcxtDataFeed
from app.feeds.coinglass_v4 import CoinglassV4
from app.signal_engine.config import SignalSettings
from app.signal_engine.context import ContextCache
from app.signal_engine.engine import SignalEngine
from app.signal_engine.market_data import (
    CcxtOnlyProvider,
    CoinglassProvider,
    MarketDataProvider,
)
from app.signal_engine.multi_tf import MultiTimeframeCollector
from app.signal_engine.notifier import TelegramSignalNotifier

logger = logging.getLogger(__name__)


class CcxtOHLCVFeed:
    """Read-only multi-timeframe OHLCV via a ccxt async exchange.

    Kept in the runner (not the package) so ``app.signal_engine`` stays
    import-light and removable. Separate from ``CcxtDataFeed`` (which is locked
    to 1m): this one fetches any timeframe the multi-TF collector asks for.
    """

    def __init__(self, exchange_id: str = "okx") -> None:
        exchange_cls = getattr(ccxt_async, exchange_id, None)
        if exchange_cls is None:
            raise ValueError(f"Unknown exchange: {exchange_id}")
        self._exchange = exchange_cls({"enableRateLimit": True})

    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> list[list[float]]:
        return await self._exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

    async def close(self) -> None:
        await self._exchange.close()


def _build_provider(settings: SignalSettings, feed: CcxtDataFeed) -> MarketDataProvider:
    """Coinglass-enriched provider when a key is set; honest ccxt-only fallback otherwise.

    Both the data feed and the Coinglass client are wired HERE (in the script),
    not inside the package, so app.signal_engine stays import-light and removable.
    """
    if settings.coinglass_api_key:
        logger.info("Coinglass key present — liquidity/OI factors use real data")
        return CoinglassProvider(feed, CoinglassV4(settings.coinglass_api_key))

    logger.warning(
        "SIGNAL_COINGLASS_API_KEY not set — liquidity-zone and OI factors will be "
        "reported as 'данные недоступны' and never counted toward setup quality"
    )
    return CcxtOnlyProvider(feed)


async def _main() -> None:
    settings = SignalSettings()
    logging.basicConfig(level=settings.log_level)

    feed = CcxtDataFeed(exchange_id="okx")
    provider = _build_provider(settings, feed)

    # Multi-timeframe candles (eval/setup/entry per scan + cached context D/12h).
    ohlcv_feed = CcxtOHLCVFeed(exchange_id="okx")
    collector = MultiTimeframeCollector(ohlcv_feed, provider, settings)
    context_cache = ContextCache(feed=ohlcv_feed, settings=settings)

    notifier = TelegramSignalNotifier(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )
    engine = SignalEngine(
        settings=settings,
        notifier=notifier,
        collector=collector,
        context_cache=context_cache,
    )

    try:
        await engine.run_forever()
    finally:
        await feed.close()
        await ohlcv_feed.close()


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
