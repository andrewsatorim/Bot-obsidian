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
    """Catches MAJOR trend reversals only — very selective.

    STRICT entry (all required):
    1. RSI extreme (< 20 or > 80) — deep oversold/overbought
    2. RSI divergence on wide window (30 bars)
    3. Price structure confirmation: first higher-high (LONG) or lower-low (SHORT)
       after the extreme — proves reversal has STARTED
    4. At least 1 of: volume climax OR OI expansion

    Regime: only LONG from TREND_DOWN, SHORT from TREND_UP.
    Cooldown: 40 bars (20 hours) between trades.
    Exit: trailing stop 3.5 ATR, no TP.
    """

    def __init__(self, symbol: str = "BTC/USDT",
                 rsi_extreme_low: float = 20.0,
                 rsi_extreme_high: float = 80.0,
                 rsi_period: int = 14,
                 volume_threshold: float = 1.3,
                 divergence_window: int = 30,
                 cooldown_bars: int = 40) -> None:
        self._symbol = symbol
        self._rsi_extreme_low = rsi_extreme_low
        self._rsi_extreme_high = rsi_extreme_high
        self._rsi_period = rsi_period
        self._volume_threshold = volume_threshold
        self._divergence_window = divergence_window
        self._cooldown_bars = cooldown_bars
        self._price_history: deque[float] = deque(maxlen=80)
        self._rsi_history: deque[float] = deque(maxlen=80)
        # Track if we're in "ready" state (divergence + extreme detected)
        self._ready_long: bool = False
        self._ready_short: bool = False
        self._ready_bar: int = -100
        self._ready_low: float = float("inf")   # lowest price during ready state (for LONG)
        self._ready_high: float = 0.0            # highest price during ready state (for SHORT)
        self._last_signal_bar: int = -100
        # RSI state
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

    def _has_bullish_divergence(self) -> bool:
        """Price lower low + RSI higher low over wide window."""
        w = self._divergence_window
        if len(self._rsi_history) < w:
            return False
        prices = list(self._price_history)[-w:]
        rsis = list(self._rsi_history)[-w:]
        third = w // 3
        if third < 3:
            return False
        # Compare first third vs last third for clearer divergence
        p_first = prices[:third]
        p_last = prices[-third:]
        r_first = rsis[:third]
        r_last = rsis[-third:]
        return min(p_last) < min(p_first) and min(r_last) > min(r_first)

    def _has_bearish_divergence(self) -> bool:
        """Price higher high + RSI lower high over wide window."""
        w = self._divergence_window
        if len(self._rsi_history) < w:
            return False
        prices = list(self._price_history)[-w:]
        rsis = list(self._rsi_history)[-w:]
        third = w // 3
        if third < 3:
            return False
        p_first = prices[:third]
        p_last = prices[-third:]
        r_first = rsis[:third]
        r_last = rsis[-third:]
        return max(p_last) > max(p_first) and max(r_last) < max(r_first)

    def generate_signal(self, features: FeatureVector) -> Optional[Signal]:
        price = features.price
        rsi = self._update_rsi(price)
        self._rsi_history.append(rsi)

        if self._bar_count < self._divergence_window + 5:
            return None

        # --- Phase 1: Detect "ready" state (extreme RSI + divergence) ---

        # Check for LONG setup: RSI < 20 + bullish divergence
        if rsi < self._rsi_extreme_low and self._has_bullish_divergence():
            if features.regime_label == RegimeLabel.TREND_DOWN:
                self._ready_long = True
                self._ready_short = False
                self._ready_bar = self._bar_count
                self._ready_low = price

        # Check for SHORT setup: RSI > 80 + bearish divergence
        if rsi > self._rsi_extreme_high and self._has_bearish_divergence():
            if features.regime_label == RegimeLabel.TREND_UP:
                self._ready_short = True
                self._ready_long = False
                self._ready_bar = self._bar_count
                self._ready_high = price

        # Ready state expires after 15 bars
        if self._bar_count - self._ready_bar > 15:
            self._ready_long = False
            self._ready_short = False

        # Cooldown
        if self._bar_count - self._last_signal_bar < self._cooldown_bars:
            return None

        # --- Phase 2: Wait for price confirmation ---

        if self._ready_long:
            # Track the lowest price since ready
            self._ready_low = min(self._ready_low, price)
            # Confirm: price made a higher high (bounced from low)
            bounce_pct = (price - self._ready_low) / self._ready_low if self._ready_low > 0 else 0
            if bounce_pct > 0.005:  # 0.5% bounce from low
                # Additional filter: volume or OI
                has_confirmation = (features.volume_ratio >= self._volume_threshold or
                                    features.oi_trend > 0)
                if has_confirmation:
                    self._ready_long = False
                    self._last_signal_bar = self._bar_count
                    strength = min(bounce_pct * 10, 1.0)
                    return Signal(
                        symbol=self._symbol,
                        direction=Direction.LONG,
                        strength=max(strength, 0.3),
                        timestamp=int(time.time()),
                    )

        if self._ready_short:
            self._ready_high = max(self._ready_high, price)
            drop_pct = (self._ready_high - price) / self._ready_high if self._ready_high > 0 else 0
            if drop_pct > 0.005:  # 0.5% drop from high
                has_confirmation = (features.volume_ratio >= self._volume_threshold or
                                    features.oi_trend > 0)
                if has_confirmation:
                    self._ready_short = False
                    self._last_signal_bar = self._bar_count
                    strength = min(drop_pct * 10, 1.0)
                    return Signal(
                        symbol=self._symbol,
                        direction=Direction.SHORT,
                        strength=max(strength, 0.3),
                        timestamp=int(time.time()),
                    )

        return None
