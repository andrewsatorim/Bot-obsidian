from __future__ import annotations

import logging
from collections import deque
from typing import Optional

from app.models.enums import Direction, RegimeLabel
from app.models.feature_vector import FeatureVector
from app.models.signal import Signal
from app.ports.strategy_port import StrategyPort

import time

logger = logging.getLogger(__name__)


class ReversalStrategy(StrategyPort):
    """Catches major trend reversals using multi-signal confirmation.

    Entry conditions (all must be true):
    1. RSI extreme: RSI < 25 (oversold->LONG) or RSI > 75 (overbought->SHORT)
    2. RSI divergence: price makes new low but RSI doesn't (or inverse for SHORT)
    3. EMA crossover: fast EMA(9) crosses slow EMA(21) in reversal direction
    4. Volume climax: volume > 1.8x average (capitulation/climax)
    5. OI expansion: new money entering (oi_trend > 0.005)

    Exit: trailing stop only, no TP levels.
    """

    def __init__(self, symbol: str = "BTC/USDT",
                 rsi_oversold: float = 25.0,
                 rsi_overbought: float = 75.0,
                 volume_climax: float = 1.8,
                 oi_min: float = 0.005,
                 lookback: int = 20) -> None:
        self._symbol = symbol
        self._rsi_oversold = rsi_oversold
        self._rsi_overbought = rsi_overbought
        self._volume_climax = volume_climax
        self._oi_min = oi_min
        self._lookback = lookback
        # Track recent prices and RSI for divergence detection
        self._price_history: deque[float] = deque(maxlen=50)
        self._rsi_history: deque[float] = deque(maxlen=50)
        self._ema_fast_history: deque[float] = deque(maxlen=5)
        self._ema_slow_history: deque[float] = deque(maxlen=5)

    def _detect_bullish_divergence(self) -> bool:
        """Price makes lower low but RSI makes higher low."""
        if len(self._price_history) < self._lookback or len(self._rsi_history) < self._lookback:
            return False
        prices = list(self._price_history)
        rsis = list(self._rsi_history)

        # Find the lowest price in recent history
        recent_prices = prices[-self._lookback:]
        recent_rsis = rsis[-self._lookback:]

        # Split into two halves to compare
        half = len(recent_prices) // 2
        first_half_prices = recent_prices[:half]
        second_half_prices = recent_prices[half:]
        first_half_rsis = recent_rsis[:half]
        second_half_rsis = recent_rsis[half:]

        if not first_half_prices or not second_half_prices:
            return False

        # Bullish divergence: price lower low, RSI higher low
        price_lower = min(second_half_prices) < min(first_half_prices)
        rsi_higher = min(second_half_rsis) > min(first_half_rsis)

        return price_lower and rsi_higher

    def _detect_bearish_divergence(self) -> bool:
        """Price makes higher high but RSI makes lower high."""
        if len(self._price_history) < self._lookback or len(self._rsi_history) < self._lookback:
            return False
        prices = list(self._price_history)
        rsis = list(self._rsi_history)

        recent_prices = prices[-self._lookback:]
        recent_rsis = rsis[-self._lookback:]

        half = len(recent_prices) // 2
        first_half_prices = recent_prices[:half]
        second_half_prices = recent_prices[half:]
        first_half_rsis = recent_rsis[:half]
        second_half_rsis = recent_rsis[half:]

        if not first_half_prices or not second_half_prices:
            return False

        # Bearish divergence: price higher high, RSI lower high
        price_higher = max(second_half_prices) > max(first_half_prices)
        rsi_lower = max(second_half_rsis) < max(first_half_rsis)

        return price_higher and rsi_lower

    def _ema_crossover(self, direction: Direction) -> bool:
        """Check if fast EMA just crossed slow EMA in the given direction."""
        if len(self._ema_fast_history) < 2 or len(self._ema_slow_history) < 2:
            return False

        fast_now = self._ema_fast_history[-1]
        fast_prev = self._ema_fast_history[-2]
        slow_now = self._ema_slow_history[-1]
        slow_prev = self._ema_slow_history[-2]

        if direction == Direction.LONG:
            # Bullish cross: fast was below slow, now above
            return fast_prev <= slow_prev and fast_now > slow_now
        else:
            # Bearish cross: fast was above slow, now below
            return fast_prev >= slow_prev and fast_now < slow_now

    def generate_signal(self, features: FeatureVector) -> Optional[Signal]:
        # Update histories
        self._price_history.append(features.price)
        self._rsi_history.append(features.rsi)

        # Compute simple EMAs from price history for crossover detection
        prices = list(self._price_history)
        if len(prices) >= 21:
            ema9 = sum(prices[-9:]) / 9  # simplified
            ema21 = sum(prices[-21:]) / 21
            self._ema_fast_history.append(ema9)
            self._ema_slow_history.append(ema21)

        # Need enough history
        if len(self._price_history) < self._lookback:
            return None

        direction = None
        divergence = False

        # Check LONG reversal (oversold + bullish divergence)
        if features.rsi < self._rsi_oversold:
            if self._detect_bullish_divergence():
                divergence = True
                direction = Direction.LONG

        # Check SHORT reversal (overbought + bearish divergence)
        elif features.rsi > self._rsi_overbought:
            if self._detect_bearish_divergence():
                divergence = True
                direction = Direction.SHORT

        if direction is None:
            return None

        # EMA crossover confirmation
        if not self._ema_crossover(direction):
            logger.debug("reversal rejected: no EMA crossover for %s", direction.value)
            return None

        # Volume climax confirmation
        if features.volume_ratio < self._volume_climax:
            logger.debug("reversal rejected: volume_ratio=%.2f < %.2f",
                        features.volume_ratio, self._volume_climax)
            return None

        # OI expansion (new money entering)
        if features.oi_trend < self._oi_min:
            logger.debug("reversal rejected: oi_trend=%.4f < %.4f",
                        features.oi_trend, self._oi_min)
            return None

        # Calculate signal strength
        # RSI extremity contributes to strength
        if direction == Direction.LONG:
            rsi_strength = max(0, (self._rsi_oversold - features.rsi) / self._rsi_oversold)
        else:
            rsi_strength = max(0, (features.rsi - self._rsi_overbought) / (100 - self._rsi_overbought))

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
        logger.info("REVERSAL signal: %s strength=%.2f rsi=%.1f vol_ratio=%.2f divergence=%s",
                    direction.value, strength, features.rsi, features.volume_ratio, divergence)
        return signal
