from __future__ import annotations

import logging
import time
from typing import Optional

from app.models.enums import Direction, RegimeLabel
from app.models.feature_vector import FeatureVector
from app.models.signal import Signal
from app.ports.strategy_port import StrategyPort

logger = logging.getLogger(__name__)


class BreakoutNoOIStrategy(StrategyPort):
    """Breakout without OI filter — for exchanges without OI data.

    Entry: regime trending + strong volume spike (higher threshold).
    Stricter volume filter compensates for missing OI confirmation.
    """

    def __init__(self, symbol: str = "BTC/USDT",
                 volume_min: float = 1.5,
                 cooldown_bars: int = 15) -> None:
        self._symbol = symbol
        self._volume_min = volume_min
        self._cooldown = cooldown_bars
        self._bar_count = 0
        self._last_signal_bar = -100
        self._last_direction: Direction | None = None

    def generate_signal(self, features: FeatureVector) -> Optional[Signal]:
        self._bar_count += 1

        if features.regime_label == RegimeLabel.TREND_UP:
            direction = Direction.LONG
        elif features.regime_label == RegimeLabel.TREND_DOWN:
            direction = Direction.SHORT
        else:
            return None

        # Cooldown
        if self._bar_count - self._last_signal_bar < self._cooldown:
            return None

        # Stricter volume filter (no OI to confirm)
        if features.volume_ratio < self._volume_min:
            return None

        # Don't repeat same direction without reversal
        if direction == self._last_direction:
            return None

        self._last_signal_bar = self._bar_count
        self._last_direction = direction

        strength = min(features.volume_ratio / 3.0, 1.0)
        strength = max(strength, 0.2)

        return Signal(
            symbol=self._symbol,
            direction=direction,
            strength=strength,
            timestamp=int(time.time()),
        )
