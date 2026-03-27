from __future__ import annotations

import logging
import time
from collections import deque
from typing import Optional

from app.models.enums import Direction
from app.models.feature_vector import FeatureVector
from app.models.signal import Signal
from app.ports.strategy_port import StrategyPort

logger = logging.getLogger(__name__)


class SwingStrategy(StrategyPort):
    """Swing trading — catches multi-day trends on 4h timeframe.

    Entry: EMA(9) crosses EMA(21) + price confirmation + volume.
    Exit: wide trailing stop only (rides the whole trend).
    Expects 2-5 trades per month, each lasting days to weeks.
    """

    def __init__(self, symbol: str = "BTC/USDT",
                 ema_fast: int = 9,
                 ema_slow: int = 21,
                 volume_threshold: float = 1.2,
                 cooldown_bars: int = 6) -> None:  # 6 bars * 4h = 24h cooldown
        self._symbol = symbol
        self._ema_fast_period = ema_fast
        self._ema_slow_period = ema_slow
        self._volume_threshold = volume_threshold
        self._cooldown_bars = cooldown_bars
        self._price_history: deque[float] = deque(maxlen=100)
        self._ema_fast: float | None = None
        self._ema_slow: float | None = None
        self._prev_ema_fast: float | None = None
        self._prev_ema_slow: float | None = None
        self._last_signal_bar: int = -100
        self._last_direction: Direction | None = None
        self._bar_count: int = 0

    def _update_emas(self, price: float) -> None:
        self._price_history.append(price)
        self._bar_count += 1
        self._prev_ema_fast = self._ema_fast
        self._prev_ema_slow = self._ema_slow

        # EMA fast
        if self._ema_fast is None:
            if self._bar_count >= self._ema_fast_period:
                self._ema_fast = sum(list(self._price_history)[-self._ema_fast_period:]) / self._ema_fast_period
        else:
            k = 2.0 / (self._ema_fast_period + 1)
            self._ema_fast = price * k + self._ema_fast * (1 - k)

        # EMA slow
        if self._ema_slow is None:
            if self._bar_count >= self._ema_slow_period:
                self._ema_slow = sum(list(self._price_history)[-self._ema_slow_period:]) / self._ema_slow_period
        else:
            k = 2.0 / (self._ema_slow_period + 1)
            self._ema_slow = price * k + self._ema_slow * (1 - k)

    def generate_signal(self, features: FeatureVector) -> Optional[Signal]:
        price = features.price
        self._update_emas(price)

        if (self._ema_fast is None or self._ema_slow is None or
                self._prev_ema_fast is None or self._prev_ema_slow is None):
            return None

        # Cooldown
        if self._bar_count - self._last_signal_bar < self._cooldown_bars:
            return None

        direction = None

        # Bullish cross: EMA fast crosses above EMA slow
        if self._prev_ema_fast <= self._prev_ema_slow and self._ema_fast > self._ema_slow:
            # Price must be above both EMAs (confirms uptrend starting)
            if price > self._ema_fast:
                direction = Direction.LONG

        # Bearish cross: EMA fast crosses below EMA slow
        elif self._prev_ema_fast >= self._prev_ema_slow and self._ema_fast < self._ema_slow:
            # Price must be below both EMAs
            if price < self._ema_fast:
                direction = Direction.SHORT

        if direction is None:
            return None

        # Don't repeat same direction
        if direction == self._last_direction:
            return None

        # Volume confirmation (relaxed — just needs above average)
        if features.volume_ratio < self._volume_threshold:
            return None

        self._last_signal_bar = self._bar_count
        self._last_direction = direction

        # Strength based on EMA separation
        ema_spread = abs(self._ema_fast - self._ema_slow) / price
        strength = min(ema_spread * 100, 1.0)
        strength = max(strength, 0.3)

        signal = Signal(
            symbol=self._symbol,
            direction=direction,
            strength=strength,
            timestamp=int(time.time()),
        )
        logger.info("SWING %s ema_fast=%.2f ema_slow=%.2f vol=%.2f",
                     direction.value, self._ema_fast, self._ema_slow, features.volume_ratio)
        return signal
