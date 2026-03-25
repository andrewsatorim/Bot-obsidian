from __future__ import annotations

import logging
import time
from typing import Optional

from app.models.enums import Direction, RegimeLabel
from app.models.feature_vector import FeatureVector
from app.models.signal import Signal
from app.ports.strategy_port import StrategyPort

logger = logging.getLogger(__name__)

FUNDING_ZSCORE_THRESHOLD = 2.0
MAX_VOLATILITY = 0.05
NEWS_OPPOSITION_THRESHOLD = 0.5


class FundingMeanReversionStrategy(StrategyPort):
    """Generates signals based on extreme funding rate z-scores.

    Logic:
    - funding_zscore > 2.0 and regime is not TREND_UP -> SHORT (funding too positive)
    - funding_zscore < -2.0 and regime is not TREND_DOWN -> LONG (funding too negative)
    """

    def __init__(self, symbol: str = "BTC/USDT") -> None:
        self._symbol = symbol

    def generate_signal(self, features: FeatureVector) -> Optional[Signal]:
        fz = features.funding_zscore

        if abs(fz) < FUNDING_ZSCORE_THRESHOLD:
            return None

        # Determine direction
        if fz > FUNDING_ZSCORE_THRESHOLD:
            direction = Direction.SHORT
        else:
            direction = Direction.LONG

        # Regime filter
        if direction == Direction.SHORT and features.regime_label == RegimeLabel.TREND_UP:
            logger.debug("signal rejected: SHORT in TREND_UP regime")
            return None
        if direction == Direction.LONG and features.regime_label == RegimeLabel.TREND_DOWN:
            logger.debug("signal rejected: LONG in TREND_DOWN regime")
            return None

        # Volatility filter
        if features.volatility_regime > MAX_VOLATILITY:
            logger.debug("signal rejected: volatility_regime=%.4f > %.4f", features.volatility_regime, MAX_VOLATILITY)
            return None

        # News opposition filter
        if direction == Direction.LONG and features.news_score < -NEWS_OPPOSITION_THRESHOLD:
            logger.debug("signal rejected: news opposes LONG (score=%.2f)", features.news_score)
            return None
        if direction == Direction.SHORT and features.news_score > NEWS_OPPOSITION_THRESHOLD:
            logger.debug("signal rejected: news opposes SHORT (score=%.2f)", features.news_score)
            return None

        strength = min(abs(fz) / 4.0, 1.0)

        signal = Signal(
            symbol=self._symbol,
            direction=direction,
            strength=strength,
            timestamp=int(time.time()),
        )
        logger.info("signal generated: %s strength=%.2f funding_z=%.2f", direction.value, strength, fz)
        return signal
