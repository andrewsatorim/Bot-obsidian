"""Multi-timeframe candle collection for the signal engine (read-only).

Defines the minimal read-only OHLCV surface the engine needs (a Protocol), a
helper to turn raw ccxt OHLCV rows into a :class:`MarketDataBundle`, and a
collector that gathers — every scan — the setup, entry and evaluation
timeframes for one symbol. Coinglass liquidity/OI (timeframe-independent) comes
from the existing :class:`MarketDataProvider` and is folded into the setup
bundle so the existing four factors keep working.

This module imports no exchange client: the concrete ccxt OHLCV feed is wired in
``scripts/run_signal_engine.py`` (keeps the package import-light and removable).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from app.models.market_data_bundle import MarketDataBundle
from app.models.market_snapshot import MarketSnapshot
from app.signal_engine.config import SignalSettings
from app.signal_engine.market_data import FactorAvailability, MarketDataProvider

logger = logging.getLogger(__name__)


class OHLCVFeed(Protocol):
    """Read-only per-timeframe candle source (e.g. a ccxt async exchange wrapper)."""

    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> list[list[float]]: ...


def bundle_from_ohlcv(symbol: str, ohlcv: list[list[float]]) -> MarketDataBundle:
    """Build a read-only bundle from raw ccxt OHLCV rows ``[ts, o, h, l, c, v]``."""
    closes = [float(r[4]) for r in ohlcv] if ohlcv else []
    volumes = [float(r[5]) for r in ohlcv] if ohlcv else []
    if not closes:
        closes = [0.01]
    if not volumes:
        volumes = [0.0]
    last_price = max(closes[-1], 0.01)
    timestamp = int(ohlcv[-1][0]) if ohlcv else 1
    return MarketDataBundle(
        market=MarketSnapshot(
            symbol=symbol,
            price=last_price,
            volume=max(volumes[-1], 0.0),
            bid=last_price,
            ask=last_price,
            timestamp=max(timestamp, 1),
        ),
        price_history=closes,
        volume_history=volumes,
    )


@dataclass(frozen=True)
class MultiTFData:
    """All timeframes needed to score one symbol on one scan.

    ``setup`` is the setup-timeframe bundle, enriched with Coinglass liquidity/OI
    so the existing four factors can be evaluated on it. ``evals`` maps each
    evaluation timeframe to its bundle (the direction-vote panel). ``entry`` is
    the entry-timeframe bundle (momentum). ``availability`` is the Coinglass
    tri-state availability for the liquidity/OI factors.
    """

    setup: MarketDataBundle
    entry: MarketDataBundle
    evals: dict[str, MarketDataBundle]
    availability: FactorAvailability


class MultiTimeframeCollector:
    """Gathers the per-scan timeframes for a symbol from an OHLCV feed.

    Coinglass liquidity/OI + availability come from the injected ``provider``
    (the existing ccxt-only / Coinglass providers); only its liquidity/OI fields
    are used — its own (1m) candles are irrelevant to the multi-TF panel.
    """

    def __init__(
        self,
        ohlcv_feed: OHLCVFeed,
        provider: MarketDataProvider,
        settings: SignalSettings,
    ) -> None:
        self._feed = ohlcv_feed
        self._provider = provider
        self._settings = settings

    async def collect(self, symbol: str) -> MultiTFData:
        s = self._settings
        cg = await self._provider.fetch(symbol)  # Coinglass liquidity/OI + availability

        # Fetch each distinct timeframe once (setup TF usually also in eval set).
        needed = {s.setup_timeframe, s.entry_timeframe, *s.eval_timeframes}
        bundles: dict[str, MarketDataBundle] = {}
        for tf in needed:
            ohlcv = await self._feed.fetch_ohlcv(symbol, tf, s.ohlcv_limit)
            bundles[tf] = bundle_from_ohlcv(symbol, ohlcv)

        # Fold timeframe-independent Coinglass data into the setup bundle so the
        # existing liquidity/OI factors read it from the setup-TF features.
        setup_bundle = bundles[s.setup_timeframe].model_copy(
            update={
                "liquidation_above": cg.bundle.liquidation_above,
                "liquidation_below": cg.bundle.liquidation_below,
                "oi_history": cg.bundle.oi_history,
            }
        )
        return MultiTFData(
            setup=setup_bundle,
            entry=bundles[s.entry_timeframe],
            evals={tf: bundles[tf] for tf in s.eval_timeframes},
            availability=cg.availability,
        )
