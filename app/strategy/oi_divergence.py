from __future__ import annotations

import logging
import time
from typing import Optional

from app.models.enums import Direction, RegimeLabel
from app.models.feature_vector import FeatureVector
from app.models.signal import Signal
from app.ports.strategy_port import StrategyPort

logger = logging.getLogger(__name__)


class OIDivergenceStrategy(StrategyPort):
    """OI Divergence with enhanced entry filters.

    Core: Price UP + OI DOWN = weak rally -> SHORT (and vice versa)

    Filters (all must pass):
    1. OI trend must be strong (< -0.03, not just -0.01)
    2. Volume confirmation (> 1.3x average)
    3. Regime must be TREND_UP or TREND_DOWN (not RANGE)
    4. Minimum strength threshold 0.5
    5. Cooldown: min_bars between signals
    """

    def __init__(
        self,
        symbol: str = "BTC/USDT:USDT",
        oi_threshold: float = -0.03,        # Strong divergence only (was -0.01)
        min_volume_ratio: float = 1.3,      # Volume must confirm
        min_strength: float = 0.5,          # Only strong signals (was 0.35)
        max_volatility: float = 0.06,       # Skip extreme volatility
        cooldown_bars: int = 6,             # Min 3 hours between entries (30min TF)
        inverse: bool = False,              # Flip all signals LONG<->SHORT
    ) -> None:
        self._symbol = symbol
        self._oi_threshold = oi_threshold
        self._min_volume_ratio = min_volume_ratio
        self._min_strength = min_strength
        self._max_volatility = max_volatility
        self._cooldown_bars = cooldown_bars
        self._inverse = inverse
        self._bars_since_signal = 999  # Start ready

    def generate_signal(self, features: FeatureVector) -> Optional[Signal]:
        self._bars_since_signal += 1

        oi_trend = features.oi_trend
        price = features.price
        atr = features.atr

        if atr == 0 or price == 0:
            return None

        # Filter 1: Strong OI divergence only
        if oi_trend >= self._oi_threshold:
            return None

        # Filter 2: Must be in a clear trend (not RANGE/VOLATILE)
        if features.regime_label == RegimeLabel.TREND_UP:
            direction = Direction.SHORT
        elif features.regime_label == RegimeLabel.TREND_DOWN:
            direction = Direction.LONG
        else:
            return None  # No range trading — this was source of bad trades

        # Filter 3: Volume confirmation
        if features.volume_ratio < self._min_volume_ratio:
            return None

        # Filter 4: Skip extreme volatility
        if features.volatility_regime > self._max_volatility:
            return None

        # Filter 5: Cooldown between signals
        if self._bars_since_signal < self._cooldown_bars:
            return None

        # Filter 6: Funding alignment (SHORT needs positive funding, LONG needs negative)
        if direction == Direction.SHORT and features.funding_zscore < 0:
            return None  # Funding already favors shorts — no divergence edge
        if direction == Direction.LONG and features.funding_zscore > 0:
            return None  # Funding already favors longs

        # Strength: based on OI divergence magnitude + volume
        oi_magnitude = abs(oi_trend)
        strength = min(0.4 + oi_magnitude * 5.0, 1.0)
        if features.volume_ratio > 1.5:
            strength = min(strength + 0.1, 1.0)

        # Filter 7: Minimum strength
        if strength < self._min_strength:
            return None

        self._bars_since_signal = 0

        # Inverse mode: flip direction
        if self._inverse:
            direction = Direction.SHORT if direction == Direction.LONG else Direction.LONG

        signal = Signal(
            symbol=self._symbol,
            direction=direction,
            strength=strength,
            timestamp=int(time.time()),
        )
        logger.info(
            "OI divergence: %s str=%.2f oi=%.4f vol=%.2f fund_z=%.2f regime=%s",
            direction.value, strength, oi_trend, features.volume_ratio,
            features.funding_zscore, features.regime_label.value,
        )
        return signal
