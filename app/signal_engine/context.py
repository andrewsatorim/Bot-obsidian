"""Context layer: the slow macro backdrop (daily + 12h), cached.

The context direction is computed from two slow timeframes and CACHED per symbol:
it is refreshed at most once per ``context_refresh_sec`` (default a day), so the
daily/12h candles are NOT re-fetched on every scan. Each scan just reads the
cached direction.

Daily has priority: the DAILY timeframe sets the direction; the 12h timeframe
only amplifies or dampens it — an opposing 12h downgrades the daily bias to
NEUTRAL but can never flip it. A directionless (RANGE/unknown) daily means no
macro bias regardless of 12h.

Read-only: imports only the feature engine and the OHLCV feed; no execution.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

from app.analytics.feature_engine import FeatureEngine
from app.models.enums import RegimeLabel
from app.signal_engine.config import SignalSettings
from app.signal_engine.multi_tf import OHLCVFeed, bundle_from_ohlcv

logger = logging.getLogger(__name__)


class ContextDirection(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


def combine_context(daily: RegimeLabel, h12: RegimeLabel) -> ContextDirection:
    """Daily sets direction; 12h amplifies/dampens (never flips it)."""
    if daily == RegimeLabel.TREND_UP:
        # 12h trending down opposes the daily bull -> dampen to neutral, not bear.
        return ContextDirection.NEUTRAL if h12 == RegimeLabel.TREND_DOWN else ContextDirection.BULLISH
    if daily == RegimeLabel.TREND_DOWN:
        return ContextDirection.NEUTRAL if h12 == RegimeLabel.TREND_UP else ContextDirection.BEARISH
    return ContextDirection.NEUTRAL  # directionless daily -> no macro bias


@dataclass
class ContextCache:
    """Per-symbol cached macro direction, refreshed at most once per refresh window.

    ``clock`` is injectable so tests can advance time without sleeping.
    """

    feed: OHLCVFeed
    settings: SignalSettings
    feature_engine: FeatureEngine = field(default_factory=FeatureEngine)
    clock: Callable[[], float] = time.time
    _cache: dict[str, tuple[ContextDirection, float]] = field(default_factory=dict)

    async def get(self, symbol: str) -> ContextDirection:
        now = self.clock()
        hit = self._cache.get(symbol)
        if hit is not None and (now - hit[1]) < self.settings.context_refresh_sec:
            return hit[0]
        direction = await self._compute(symbol)
        self._cache[symbol] = (direction, now)
        logger.info("context refreshed for %s: %s", symbol, direction.value)
        return direction

    async def _compute(self, symbol: str) -> ContextDirection:
        tfs = self.settings.context_timeframes
        daily_tf = tfs[0]
        h12_tf = tfs[1] if len(tfs) > 1 else tfs[0]
        daily = await self._regime(symbol, daily_tf)
        h12 = await self._regime(symbol, h12_tf)
        return combine_context(daily, h12)

    async def _regime(self, symbol: str, timeframe: str) -> RegimeLabel:
        ohlcv = await self.feed.fetch_ohlcv(symbol, timeframe, self.settings.ohlcv_limit)
        features = self.feature_engine.build_features(bundle_from_ohlcv(symbol, ohlcv))
        return features.regime_label
