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
    """Catches major trend reversals using scoring system.

    Scores 5 factors (each 0 or 1 point). Signals when score >= 3.
    Factors persist for a window of bars (not just current bar).

    1. RSI extreme zone (< 30 or > 70) within last 5 bars
    2. RSI divergence within last 10 bars
    3. EMA(9)/EMA(21) crossover within last 3 bars
    4. Volume spike (> 1.3x avg)
    5. OI expansion (oi_trend > 0)

    Exit: trailing stop only, no TP.
    """

    def __init__(self, symbol: str = "BTC/USDT",
                 rsi_oversold: float = 30.0,
                 rsi_overbought: float = 70.0,
                 rsi_period: int = 14,
                 volume_threshold: float = 1.3,
                 min_score: int = 3,
                 lookback: int = 15) -> None:
        self._symbol = symbol
        self._rsi_oversold = rsi_oversold
        self._rsi_overbought = rsi_overbought
        self._rsi_period = rsi_period
        self._volume_threshold = volume_threshold
        self._min_score = min_score
        self._lookback = lookback
        self._price_history: deque[float] = deque(maxlen=60)
        self._rsi_history: deque[float] = deque(maxlen=60)
        # Track recent signals from each factor
        self._rsi_extreme_bars: deque[int] = deque(maxlen=5)  # bar indices where RSI was extreme
        self._rsi_extreme_dir: deque[Direction] = deque(maxlen=5)
        self._ema_cross_bar: int = -100  # last bar with EMA cross
        self._ema_cross_dir: Direction | None = None
        self._divergence_bar: int = -100
        self._divergence_dir: Direction | None = None
        # EMA state
        self._ema_fast: float | None = None
        self._ema_slow: float | None = None
        self._prev_ema_fast: float | None = None
        self._prev_ema_slow: float | None = None
        # RSI state (Wilder's RMA)
        self._rma_gain: float = 0.0
        self._rma_loss: float = 0.0
        self._rsi_initialized: bool = False
        self._bar_count: int = 0

    def _update_rsi(self, price: float) -> float:
        """Compute RSI using Wilder's RMA smoothing."""
        self._price_history.append(price)
        self._bar_count += 1

        if self._bar_count < 2:
            return 50.0

        prices = list(self._price_history)
        delta = prices[-1] - prices[-2]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        period = self._rsi_period

        if not self._rsi_initialized:
            if self._bar_count < period + 1:
                return 50.0
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
            self._rma_gain = (self._rma_gain * (period - 1) + gain) / period
            self._rma_loss = (self._rma_loss * (period - 1) + loss) / period

        if self._rma_loss == 0:
            return 100.0
        rs = self._rma_gain / self._rma_loss
        return 100.0 - 100.0 / (1.0 + rs)

    def _update_ema(self, price: float) -> None:
        """Update EMA(9) and EMA(21) incrementally."""
        self._prev_ema_fast = self._ema_fast
        self._prev_ema_slow = self._ema_slow

        if self._ema_fast is None:
            if self._bar_count >= 9:
                prices = list(self._price_history)
                self._ema_fast = sum(prices[-9:]) / 9
            return
        k9 = 2.0 / 10
        self._ema_fast = price * k9 + self._ema_fast * (1 - k9)

        if self._ema_slow is None:
            if self._bar_count >= 21:
                prices = list(self._price_history)
                self._ema_slow = sum(prices[-21:]) / 21
            return
        k21 = 2.0 / 22
        self._ema_slow = price * k21 + self._ema_slow * (1 - k21)

    def _check_divergence(self, rsi: float) -> None:
        """Check for RSI divergence and store if found."""
        if len(self._rsi_history) < self._lookback:
            return
        prices = list(self._price_history)[-self._lookback:]
        rsis = list(self._rsi_history)[-self._lookback:]
        half = len(prices) // 2
        if half < 3:
            return

        # Bullish divergence
        if (min(prices[half:]) < min(prices[:half]) and
                min(rsis[half:]) > min(rsis[:half])):
            self._divergence_bar = self._bar_count
            self._divergence_dir = Direction.LONG

        # Bearish divergence
        if (max(prices[half:]) > max(prices[:half]) and
                max(rsis[half:]) < max(rsis[:half])):
            self._divergence_bar = self._bar_count
            self._divergence_dir = Direction.SHORT

    def _check_ema_cross(self) -> None:
        """Check for EMA crossover and store if found."""
        if (self._ema_fast is None or self._ema_slow is None or
                self._prev_ema_fast is None or self._prev_ema_slow is None):
            return
        # Bullish cross
        if self._prev_ema_fast <= self._prev_ema_slow and self._ema_fast > self._ema_slow:
            self._ema_cross_bar = self._bar_count
            self._ema_cross_dir = Direction.LONG
        # Bearish cross
        elif self._prev_ema_fast >= self._prev_ema_slow and self._ema_fast < self._ema_slow:
            self._ema_cross_bar = self._bar_count
            self._ema_cross_dir = Direction.SHORT

    def generate_signal(self, features: FeatureVector) -> Optional[Signal]:
        price = features.price
        rsi = self._update_rsi(price)
        self._update_ema(price)
        self._rsi_history.append(rsi)

        # Track RSI extremes
        if rsi < self._rsi_oversold:
            self._rsi_extreme_bars.append(self._bar_count)
            self._rsi_extreme_dir.append(Direction.LONG)
        elif rsi > self._rsi_overbought:
            self._rsi_extreme_bars.append(self._bar_count)
            self._rsi_extreme_dir.append(Direction.SHORT)

        # Check divergence and EMA cross (store for window)
        self._check_divergence(rsi)
        self._check_ema_cross()

        if self._bar_count < max(self._lookback, 22):
            return None

        # --- Scoring system for each direction ---
        for direction in [Direction.LONG, Direction.SHORT]:
            score = 0
            reasons = []

            # 1. RSI extreme within last 5 bars
            for i in range(len(self._rsi_extreme_bars)):
                if (self._bar_count - self._rsi_extreme_bars[i] <= 5 and
                        self._rsi_extreme_dir[i] == direction):
                    score += 1
                    reasons.append("RSI")
                    break

            # 2. RSI divergence within last 10 bars
            if (self._bar_count - self._divergence_bar <= 10 and
                    self._divergence_dir == direction):
                score += 1
                reasons.append("DIV")

            # 3. EMA crossover within last 3 bars
            if (self._bar_count - self._ema_cross_bar <= 3 and
                    self._ema_cross_dir == direction):
                score += 1
                reasons.append("EMA")

            # 4. Volume spike (current bar)
            if features.volume_ratio >= self._volume_threshold:
                score += 1
                reasons.append("VOL")

            # 5. OI expansion (current bar)
            if features.oi_trend > 0:
                score += 1
                reasons.append("OI")

            if score >= self._min_score:
                strength = min(score / 5.0, 1.0)
                signal = Signal(
                    symbol=self._symbol,
                    direction=direction,
                    strength=strength,
                    timestamp=int(time.time()),
                )
                logger.info("REVERSAL %s score=%d/5 [%s] rsi=%.1f vol=%.2f",
                            direction.value, score, "+".join(reasons),
                            rsi, features.volume_ratio)
                return signal

        return None
