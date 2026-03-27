from __future__ import annotations

import logging
import time
from collections import deque
from typing import Optional

from app.models.enums import Direction, RegimeLabel
from app.models.feature_vector import FeatureVector
from app.models.signal import Signal
from app.ports.strategy_port import StrategyPort

logger = logging.getLogger(__name__)


class ReversalStrategy(StrategyPort):
    """Catches major trend reversals — strict entry, wide trailing stop.

    MANDATORY: RSI divergence must be present.
    Then score 3 additional factors (need >= 2 of 4):
    1. RSI in extreme zone (< 30 or > 70) within last 5 bars
    2. EMA(9)/EMA(21) crossover within last 3 bars
    3. Volume climax (> 1.5x avg)
    4. OI expansion (oi_trend > 0)

    Regime filter: only LONG from TREND_DOWN, only SHORT from TREND_UP.
    Cooldown: minimum 20 bars between trades.
    """

    def __init__(self, symbol: str = "BTC/USDT",
                 rsi_oversold: float = 30.0,
                 rsi_overbought: float = 70.0,
                 rsi_period: int = 14,
                 volume_threshold: float = 1.5,
                 min_extra_score: int = 2,
                 lookback: int = 20,
                 cooldown_bars: int = 20) -> None:
        self._symbol = symbol
        self._rsi_oversold = rsi_oversold
        self._rsi_overbought = rsi_overbought
        self._rsi_period = rsi_period
        self._volume_threshold = volume_threshold
        self._min_extra_score = min_extra_score
        self._lookback = lookback
        self._cooldown_bars = cooldown_bars
        self._price_history: deque[float] = deque(maxlen=60)
        self._rsi_history: deque[float] = deque(maxlen=60)
        self._rsi_extreme_bars: deque[int] = deque(maxlen=10)
        self._rsi_extreme_dir: deque[Direction] = deque(maxlen=10)
        self._ema_cross_bar: int = -100
        self._ema_cross_dir: Direction | None = None
        self._divergence_bar: int = -100
        self._divergence_dir: Direction | None = None
        self._last_signal_bar: int = -100
        self._ema_fast: float | None = None
        self._ema_slow: float | None = None
        self._prev_ema_fast: float | None = None
        self._prev_ema_slow: float | None = None
        self._rma_gain: float = 0.0
        self._rma_loss: float = 0.0
        self._rsi_initialized: bool = False
        self._bar_count: int = 0

    def _update_rsi(self, price: float) -> float:
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
            gains, losses = [], []
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
        self._prev_ema_fast = self._ema_fast
        self._prev_ema_slow = self._ema_slow
        if self._ema_fast is None:
            if self._bar_count >= 9:
                self._ema_fast = sum(list(self._price_history)[-9:]) / 9
            return
        self._ema_fast = price * (2.0 / 10) + self._ema_fast * (1 - 2.0 / 10)
        if self._ema_slow is None:
            if self._bar_count >= 21:
                self._ema_slow = sum(list(self._price_history)[-21:]) / 21
            return
        self._ema_slow = price * (2.0 / 22) + self._ema_slow * (1 - 2.0 / 22)

    def _check_divergence(self) -> None:
        if len(self._rsi_history) < self._lookback:
            return
        prices = list(self._price_history)[-self._lookback:]
        rsis = list(self._rsi_history)[-self._lookback:]
        half = len(prices) // 2
        if half < 3:
            return
        # Bullish: price lower low, RSI higher low
        if (min(prices[half:]) < min(prices[:half]) and
                min(rsis[half:]) > min(rsis[:half])):
            self._divergence_bar = self._bar_count
            self._divergence_dir = Direction.LONG
        # Bearish: price higher high, RSI lower high
        if (max(prices[half:]) > max(prices[:half]) and
                max(rsis[half:]) < max(rsis[:half])):
            self._divergence_bar = self._bar_count
            self._divergence_dir = Direction.SHORT

    def _check_ema_cross(self) -> None:
        if (self._ema_fast is None or self._ema_slow is None or
                self._prev_ema_fast is None or self._prev_ema_slow is None):
            return
        if self._prev_ema_fast <= self._prev_ema_slow and self._ema_fast > self._ema_slow:
            self._ema_cross_bar = self._bar_count
            self._ema_cross_dir = Direction.LONG
        elif self._prev_ema_fast >= self._prev_ema_slow and self._ema_fast < self._ema_slow:
            self._ema_cross_bar = self._bar_count
            self._ema_cross_dir = Direction.SHORT

    def generate_signal(self, features: FeatureVector) -> Optional[Signal]:
        price = features.price
        rsi = self._update_rsi(price)
        self._update_ema(price)
        self._rsi_history.append(rsi)

        if rsi < self._rsi_oversold:
            self._rsi_extreme_bars.append(self._bar_count)
            self._rsi_extreme_dir.append(Direction.LONG)
        elif rsi > self._rsi_overbought:
            self._rsi_extreme_bars.append(self._bar_count)
            self._rsi_extreme_dir.append(Direction.SHORT)

        self._check_divergence()
        self._check_ema_cross()

        if self._bar_count < max(self._lookback, 22):
            return None

        # Cooldown: no signal within N bars of last one
        if self._bar_count - self._last_signal_bar < self._cooldown_bars:
            return None

        # --- Regime filter: only reverse FROM existing trend ---
        # LONG only from TREND_DOWN (catching bottom reversal)
        # SHORT only from TREND_UP (catching top reversal)
        allowed_dirs = []
        if features.regime_label == RegimeLabel.TREND_DOWN:
            allowed_dirs.append(Direction.LONG)
        elif features.regime_label == RegimeLabel.TREND_UP:
            allowed_dirs.append(Direction.SHORT)
        else:
            # RANGING — allow both but with higher bar
            allowed_dirs = [Direction.LONG, Direction.SHORT]

        for direction in allowed_dirs:
            # MANDATORY: RSI divergence within last 10 bars
            has_divergence = (self._bar_count - self._divergence_bar <= 10 and
                              self._divergence_dir == direction)
            if not has_divergence:
                continue

            # Score additional factors (need >= min_extra_score of 4)
            score = 0
            reasons = ["DIV"]

            # 1. RSI extreme within last 5 bars
            for i in range(len(self._rsi_extreme_bars)):
                if (self._bar_count - self._rsi_extreme_bars[i] <= 5 and
                        self._rsi_extreme_dir[i] == direction):
                    score += 1
                    reasons.append("RSI")
                    break

            # 2. EMA crossover within last 3 bars
            if (self._bar_count - self._ema_cross_bar <= 3 and
                    self._ema_cross_dir == direction):
                score += 1
                reasons.append("EMA")

            # 3. Volume spike
            if features.volume_ratio >= self._volume_threshold:
                score += 1
                reasons.append("VOL")

            # 4. OI expansion
            if features.oi_trend > 0:
                score += 1
                reasons.append("OI")

            if score >= self._min_extra_score:
                self._last_signal_bar = self._bar_count
                total_score = score + 1  # +1 for divergence
                strength = min(total_score / 5.0, 1.0)
                signal = Signal(
                    symbol=self._symbol,
                    direction=direction,
                    strength=strength,
                    timestamp=int(time.time()),
                )
                logger.info("REVERSAL %s score=%d/5 [%s] rsi=%.1f regime=%s",
                            direction.value, total_score, "+".join(reasons),
                            rsi, features.regime_label.value)
                return signal

        return None
