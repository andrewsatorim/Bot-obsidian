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


class ReversalStrategy(StrategyPort):
    """Catches major trend reversals using multi-signal confirmation.

    Entry conditions (all must be true):
    1. RSI extreme: RSI < 25 (oversold->LONG) or RSI > 75 (overbought->SHORT)
    2. RSI divergence: price makes new low but RSI doesn't (or inverse)
    3. EMA crossover: fast EMA(9) crosses slow EMA(21) in reversal direction
    4. Volume climax: volume > 1.8x average (capitulation/climax)
    5. OI expansion: new money entering (oi_trend > 0.005)

    Exit: trailing stop only, no TP levels.
    """

    def __init__(self, symbol: str = "BTC/USDT",
                 rsi_oversold: float = 25.0,
                 rsi_overbought: float = 75.0,
                 rsi_period: int = 14,
                 volume_climax: float = 1.8,
                 oi_min: float = 0.005,
                 lookback: int = 20) -> None:
        self._symbol = symbol
        self._rsi_oversold = rsi_oversold
        self._rsi_overbought = rsi_overbought
        self._rsi_period = rsi_period
        self._volume_climax = volume_climax
        self._oi_min = oi_min
        self._lookback = lookback
        self._price_history: deque[float] = deque(maxlen=60)
        self._rsi_history: deque[float] = deque(maxlen=60)
        self._ema_fast: float | None = None
        self._ema_slow: float | None = None
        self._prev_ema_fast: float | None = None
        self._prev_ema_slow: float | None = None
        self._rma_gain: float = 0.0
        self._rma_loss: float = 0.0
        self._rsi_initialized: bool = False
        self._bar_count: int = 0

    def _update_rsi(self, price: float) -> float:
        """Compute RSI using Wilder's RMA smoothing."""
        self._price_history.append(price)
        self._bar_count += 1

        if self._bar_count < 2:
            return 50.0  # neutral

        prices = list(self._price_history)
        delta = prices[-1] - prices[-2]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)

        period = self._rsi_period
        if not self._rsi_initialized:
            if self._bar_count < period + 1:
                return 50.0
            # Seed with SMA of first `period` changes
            gains = []
            losses = []
            for i in range(len(prices) - period, len(prices)):
                d = prices[i] - prices[i - 1]
                gains.append(max(d, 0.0))
                losses.append(max(-d, 0.0))
            self._rma_gain = sum(gains) / period
            self._rma_loss = sum(losses) / period
            self._rsi_initialized = True
        else:
            # Wilder's RMA: rma = (prev * (period-1) + value) / period
            self._rma_gain = (self._rma_gain * (period - 1) + gain) / period
            self._rma_loss = (self._rma_loss * (period - 1) + loss) / period

        if self._rma_loss == 0:
            return 100.0
        rs = self._rma_gain / self._rma_loss
        rsi = 100.0 - 100.0 / (1.0 + rs)
        return rsi

    def _update_ema(self, price: float) -> None:
        """Update EMA(9) and EMA(21) incrementally."""
        self._prev_ema_fast = self._ema_fast
        self._prev_ema_slow = self._ema_slow

        if self._ema_fast is None:
            if self._bar_count >= 9:
                prices = list(self._price_history)
                self._ema_fast = sum(prices[-9:]) / 9
            else:
                return
        else:
            k = 2.0 / (9 + 1)
            self._ema_fast = price * k + self._ema_fast * (1 - k)

        if self._ema_slow is None:
            if self._bar_count >= 21:
                prices = list(self._price_history)
                self._ema_slow = sum(prices[-21:]) / 21
            else:
                return
        else:
            k = 2.0 / (21 + 1)
            self._ema_slow = price * k + self._ema_slow * (1 - k)

    def _detect_bullish_divergence(self) -> bool:
        """Price makes lower low but RSI makes higher low."""
        if len(self._rsi_history) < self._lookback:
            return False
        prices = list(self._price_history)[-self._lookback:]
        rsis = list(self._rsi_history)[-self._lookback:]
        half = len(prices) // 2
        if half < 3:
            return False
        price_lower = min(prices[half:]) < min(prices[:half])
        rsi_higher = min(rsis[half:]) > min(rsis[:half])
        return price_lower and rsi_higher

    def _detect_bearish_divergence(self) -> bool:
        """Price makes higher high but RSI makes lower high."""
        if len(self._rsi_history) < self._lookback:
            return False
        prices = list(self._price_history)[-self._lookback:]
        rsis = list(self._rsi_history)[-self._lookback:]
        half = len(prices) // 2
        if half < 3:
            return False
        price_higher = max(prices[half:]) > max(prices[:half])
        rsi_lower = max(rsis[half:]) < max(rsis[:half])
        return price_higher and rsi_lower

    def _ema_crossover(self, direction: Direction) -> bool:
        """Check if fast EMA just crossed slow EMA."""
        if (self._ema_fast is None or self._ema_slow is None or
                self._prev_ema_fast is None or self._prev_ema_slow is None):
            return False
        if direction == Direction.LONG:
            return self._prev_ema_fast <= self._prev_ema_slow and self._ema_fast > self._ema_slow
        else:
            return self._prev_ema_fast >= self._prev_ema_slow and self._ema_fast < self._ema_slow

    def generate_signal(self, features: FeatureVector) -> Optional[Signal]:
        price = features.price

        # Update indicators
        rsi = self._update_rsi(price)
        self._update_ema(price)
        self._rsi_history.append(rsi)

        # Need enough history
        if self._bar_count < max(self._lookback, 22):
            return None

        direction = None

        # Check LONG reversal (oversold + bullish divergence)
        if rsi < self._rsi_oversold:
            if self._detect_bullish_divergence():
                direction = Direction.LONG

        # Check SHORT reversal (overbought + bearish divergence)
        elif rsi > self._rsi_overbought:
            if self._detect_bearish_divergence():
                direction = Direction.SHORT

        if direction is None:
            return None

        # EMA crossover confirmation
        if not self._ema_crossover(direction):
            return None

        # Volume climax confirmation
        if features.volume_ratio < self._volume_climax:
            return None

        # OI expansion (new money entering)
        if features.oi_trend < self._oi_min:
            return None

        # Signal strength
        if direction == Direction.LONG:
            rsi_strength = max(0, (self._rsi_oversold - rsi) / self._rsi_oversold)
        else:
            rsi_strength = max(0, (rsi - self._rsi_overbought) / (100 - self._rsi_overbought))

        vol_strength = min(features.volume_ratio / 3.0, 1.0)
        strength = (rsi_strength * 0.4 + vol_strength * 0.3 +
                    min(features.oi_trend / 0.05, 1.0) * 0.3)
        strength = max(min(strength, 1.0), 0.1)

        signal = Signal(
            symbol=self._symbol,
            direction=direction,
            strength=strength,
            timestamp=int(time.time()),
        )
        logger.info("REVERSAL signal: %s strength=%.2f rsi=%.1f vol=%.2f",
                     direction.value, strength, rsi, features.volume_ratio)
        return signal
