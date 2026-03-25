from __future__ import annotations

import logging
import time
from typing import Optional

from app.models.enums import Direction, RegimeLabel
from app.models.feature_vector import FeatureVector
from app.models.signal import Signal
from app.ports.strategy_port import StrategyPort

logger = logging.getLogger(__name__)

VOLUME_SPIKE_MIN = 1.5
OI_TREND_MIN = 0.03


class BreakoutStrategy(StrategyPort):
    """Detects breakouts confirmed by volume spike and OI expansion.

    Entry: price trending + volume spike + OI trend positive
    Direction follows the trend (TREND_UP -> LONG, TREND_DOWN -> SHORT).
    """

    def __init__(self, symbol: str = "BTC/USDT") -> None:
        self._symbol = symbol

    def generate_signal(self, features: FeatureVector) -> Optional[Signal]:
        # Only trade in trending regimes
        if features.regime_label == RegimeLabel.TREND_UP:
            direction = Direction.LONG
        elif features.regime_label == RegimeLabel.TREND_DOWN:
            direction = Direction.SHORT
        else:
            return None

        # Volume confirmation
        if not features.volume_spike and features.volume_ratio < VOLUME_SPIKE_MIN:
            return None

        # OI expansion confirms new money entering
        if features.oi_trend < OI_TREND_MIN:
            logger.debug("breakout rejected: oi_trend=%.4f < %.4f", features.oi_trend, OI_TREND_MIN)
            return None

        # News opposition filter
        if direction == Direction.LONG and features.news_score < -0.5:
            return None
        if direction == Direction.SHORT and features.news_score > 0.5:
            return None

        strength = min(features.volume_ratio / 3.0, 1.0) * min(features.oi_trend / 0.1, 1.0)
        strength = max(min(strength, 1.0), 0.1)

        signal = Signal(
            symbol=self._symbol,
            direction=direction,
            strength=strength,
            timestamp=int(time.time()),
        )
        logger.info("breakout signal: %s strength=%.2f vol_ratio=%.2f oi_trend=%.4f",
                     direction.value, strength, features.volume_ratio, features.oi_trend)
        return signal
