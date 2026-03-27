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


class DonchianStrategy(StrategyPort):
    """Donchian Channel Breakout (Turtle Trading system).

    The simplest and most proven trend-following system:
    - LONG when price breaks above N-period high (new high = strong trend)
    - SHORT when price breaks below N-period low
    - Wide trailing stop to ride the entire trend
    - Very few trades: 1-3 per month per asset

    On 4H with period=20: channel = 80 hours = 3.3 days.
    Catches exactly the multi-day/week trends visible on charts.
    """

    def __init__(self, symbol: str = "BTC/USDT",
                 channel_period: int = 20,
                 cooldown_bars: int = 5) -> None:
        self._symbol = symbol
        self._channel_period = channel_period
        self._cooldown_bars = cooldown_bars
        self._price_history: deque[float] = deque(maxlen=channel_period + 5)
        self._last_signal_bar: int = -100
        self._last_direction: Direction | None = None
        self._bar_count: int = 0

    def generate_signal(self, features: FeatureVector) -> Optional[Signal]:
        price = features.price
        self._price_history.append(price)
        self._bar_count += 1

        if len(self._price_history) < self._channel_period + 1:
            return None

        # Cooldown
        if self._bar_count - self._last_signal_bar < self._cooldown_bars:
            return None

        # Donchian channel: highest high and lowest low of last N bars
        # (excluding current bar)
        channel_prices = list(self._price_history)[:-1][-self._channel_period:]
        upper = max(channel_prices)
        lower = min(channel_prices)

        direction = None

        # Breakout above channel → new high → LONG
        if price > upper:
            direction = Direction.LONG

        # Breakdown below channel → new low → SHORT
        elif price < lower:
            direction = Direction.SHORT

        if direction is None:
            return None

        # Don't repeat same direction without reversal
        if direction == self._last_direction:
            return None

        # Volume confirmation (light filter)
        if features.volume_ratio < 1.0:
            return None

        self._last_signal_bar = self._bar_count
        self._last_direction = direction

        # Strength based on how far price broke through channel
        channel_width = upper - lower
        if channel_width > 0:
            if direction == Direction.LONG:
                breakout_pct = (price - upper) / channel_width
            else:
                breakout_pct = (lower - price) / channel_width
            strength = min(breakout_pct + 0.5, 1.0)
        else:
            strength = 0.5

        strength = max(strength, 0.3)

        signal = Signal(
            symbol=self._symbol,
            direction=direction,
            strength=strength,
            timestamp=int(time.time()),
        )
        logger.info("DONCHIAN %s price=%.2f upper=%.2f lower=%.2f vol=%.2f",
                     direction.value, price, upper, lower, features.volume_ratio)
        return signal
