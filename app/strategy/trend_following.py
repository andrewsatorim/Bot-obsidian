from __future__ import annotations

import logging
import time
from typing import Optional

from app.models.enums import Direction, RegimeLabel
from app.models.feature_vector import FeatureVector
from app.models.signal import Signal
from app.ports.strategy_port import StrategyPort

logger = logging.getLogger(__name__)


class TrendFollowingStrategy(StrategyPort):
    """Enters in the direction of a confirmed trend when volatility is moderate.

    Uses regime classification + funding alignment + low volatility for entry.
    """

    def __init__(self, symbol: str = "BTC/USDT", max_volatility: float = 0.04) -> None:
        self._symbol = symbol
        self._max_volatility = max_volatility

    def generate_signal(self, features: FeatureVector) -> Optional[Signal]:
        if features.regime_label == RegimeLabel.TREND_UP:
            direction = Direction.LONG
        elif features.regime_label == RegimeLabel.TREND_DOWN:
            direction = Direction.SHORT
        else:
            return None

        # Volatility filter — avoid entering in extreme volatility
        if features.volatility_regime > self._max_volatility:
            return None

        # Funding alignment: for LONG, negative/neutral funding is good
        # For SHORT, positive funding means longs are paying (good for shorts)
        if direction == Direction.LONG and features.funding_zscore > 1.5:
            logger.debug("trend rejected: funding too high for LONG (z=%.2f)", features.funding_zscore)
            return None
        if direction == Direction.SHORT and features.funding_zscore < -1.5:
            logger.debug("trend rejected: funding too low for SHORT (z=%.2f)", features.funding_zscore)
            return None

        # On-chain confirmation (positive = bullish, negative = bearish)
        if direction == Direction.LONG and features.onchain_score < -0.3:
            return None
        if direction == Direction.SHORT and features.onchain_score > 0.3:
            return None

        strength = 0.5 + 0.5 * min(abs(features.oi_trend) / 0.05, 1.0)
        strength = max(min(strength, 1.0), 0.1)

        signal = Signal(
            symbol=self._symbol,
            direction=direction,
            strength=strength,
            timestamp=int(time.time()),
        )
        logger.info("trend signal: %s strength=%.2f regime=%s", direction.value, strength, features.regime_label.value)
        return signal
