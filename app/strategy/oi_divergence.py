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
    """Detects divergence between price movement and Open Interest.

    Logic:
    - Price UP + OI DOWN = weak rally (longs closing, no new money) -> SHORT
    - Price DOWN + OI DOWN = weak selloff (shorts closing) -> LONG
    - Price UP + OI UP = confirmed rally (skip — no divergence)
    - Price DOWN + OI UP = confirmed selloff (skip)

    Why it works:
    - OI divergence reveals hidden weakness in a move
    - Institutional traders watch OI; retail doesn't
    - Historically one of the best edge signals on perpetuals
    - Works on all timeframes, especially 1h-4h
    """

    def __init__(
        self,
        symbol: str = "BTC/USDT:USDT",
        price_threshold: float = 0.003,  # Min price change to consider
        oi_threshold: float = -0.01,     # OI must be declining
    ) -> None:
        self._symbol = symbol
        self._price_threshold = price_threshold
        self._oi_threshold = oi_threshold

    def generate_signal(self, features: FeatureVector) -> Optional[Signal]:
        oi_trend = features.oi_trend
        price = features.price
        atr = features.atr

        if atr == 0 or price == 0:
            return None

        # Need OI to be declining (divergence condition)
        if oi_trend >= self._oi_threshold:
            return None  # OI is flat or rising — no divergence

        # Determine price direction from regime
        if features.regime_label == RegimeLabel.TREND_UP:
            # Price UP + OI DOWN = bearish divergence -> SHORT
            direction = Direction.SHORT
        elif features.regime_label == RegimeLabel.TREND_DOWN:
            # Price DOWN + OI DOWN = bullish divergence -> LONG
            direction = Direction.LONG
        else:
            # In range, use oi_delta for micro-divergence
            if features.oi_delta < 0 and features.volume_ratio > 1.0:
                # Volume up but OI down = closing positions, expect reversal
                # Use funding to determine direction
                if features.funding_zscore > 0.5:
                    direction = Direction.SHORT
                elif features.funding_zscore < -0.5:
                    direction = Direction.LONG
                else:
                    return None
            else:
                return None

        # Skip if volatility is extreme (divergence unreliable)
        if features.volatility_regime > 0.06:
            return None

        # Strength based on OI divergence magnitude
        oi_magnitude = abs(oi_trend)
        strength = min(0.35 + oi_magnitude * 5.0, 1.0)

        # Bonus for volume confirmation
        if features.volume_ratio > 1.5:
            strength = min(strength + 0.15, 1.0)

        signal = Signal(
            symbol=self._symbol,
            direction=direction,
            strength=strength,
            timestamp=int(time.time()),
        )
        logger.info(
            "OI divergence signal: %s strength=%.2f oi_trend=%.4f oi_delta=%.2f regime=%s",
            direction.value, strength, oi_trend, features.oi_delta, features.regime_label.value,
        )
        return signal
