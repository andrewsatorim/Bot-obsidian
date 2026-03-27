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


class CandleVolumeStrategy(StrategyPort):
    """Candlestick patterns + Volume analysis + Liquidation zones.

    Combines three independent signal sources:
    1. Candlestick patterns (engulfing, pin bar, 3-bar reversal)
    2. Volume climax/divergence (high volume at extremes = exhaustion)
    3. Liquidation proximity (price near liquidation clusters = magnet/bounce)

    Scoring: each source 0-2 points. Signal when total >= 3.
    Uses regime filter: only counter-trend entries (catching reversals).
    """

    def __init__(self, symbol: str = "BTC/USDT",
                 min_score: int = 3,
                 cooldown_bars: int = 15,
                 body_ratio_threshold: float = 0.6) -> None:
        self._symbol = symbol
        self._min_score = min_score
        self._cooldown_bars = cooldown_bars
        self._body_ratio = body_ratio_threshold
        # Price history for candle pattern detection
        # Each entry: (open, high, low, close, volume)
        self._candles: deque[tuple[float, float, float, float, float]] = deque(maxlen=30)
        self._prev_price: float | None = None
        self._bar_count: int = 0
        self._last_signal_bar: int = -100

    def _estimate_candle(self, price: float, volume: float) -> tuple[float, float, float, float]:
        """Estimate OHLC from close prices (approximation).
        Returns (open, high, low, close)."""
        if self._prev_price is None:
            return (price, price, price, price)
        open_p = self._prev_price
        close_p = price
        high_p = max(open_p, close_p) * 1.001  # slight wick
        low_p = min(open_p, close_p) * 0.999
        return (open_p, high_p, low_p, close_p)

    def _is_bullish_engulfing(self) -> bool:
        """Current candle fully engulfs previous bearish candle."""
        if len(self._candles) < 2:
            return False
        prev = self._candles[-2]
        curr = self._candles[-1]
        prev_open, _, _, prev_close, _ = prev
        curr_open, _, _, curr_close, _ = curr
        # Previous was bearish, current is bullish and engulfs
        return (prev_close < prev_open and  # prev bearish
                curr_close > curr_open and   # curr bullish
                curr_close > prev_open and   # engulfs body
                curr_open < prev_close)

    def _is_bearish_engulfing(self) -> bool:
        """Current candle fully engulfs previous bullish candle."""
        if len(self._candles) < 2:
            return False
        prev = self._candles[-2]
        curr = self._candles[-1]
        prev_open, _, _, prev_close, _ = prev
        curr_open, _, _, curr_close, _ = curr
        return (prev_close > prev_open and  # prev bullish
                curr_close < curr_open and   # curr bearish
                curr_open > prev_close and   # engulfs body
                curr_close < prev_open)

    def _is_bullish_pin_bar(self) -> bool:
        """Long lower wick, small body at top = rejection of lows."""
        if len(self._candles) < 1:
            return False
        o, h, l, c, _ = self._candles[-1]
        body = abs(c - o)
        total_range = h - l
        if total_range <= 0:
            return False
        lower_wick = min(o, c) - l
        # Lower wick > 60% of total range, body < 30%
        return lower_wick / total_range > 0.6 and body / total_range < 0.3

    def _is_bearish_pin_bar(self) -> bool:
        """Long upper wick, small body at bottom = rejection of highs."""
        if len(self._candles) < 1:
            return False
        o, h, l, c, _ = self._candles[-1]
        body = abs(c - o)
        total_range = h - l
        if total_range <= 0:
            return False
        upper_wick = h - max(o, c)
        return upper_wick / total_range > 0.6 and body / total_range < 0.3

    def _three_bar_reversal_bull(self) -> bool:
        """Three falling closes then a strong bullish bar."""
        if len(self._candles) < 4:
            return False
        c3 = self._candles[-4]
        c2 = self._candles[-3]
        c1 = self._candles[-2]
        c0 = self._candles[-1]
        # Three consecutive lower closes
        falling = c2[3] < c3[3] and c1[3] < c2[3]
        # Current bar is bullish with body > 50% of range
        curr_body = c0[3] - c0[0]
        curr_range = c0[1] - c0[2]
        strong_bull = curr_body > 0 and curr_range > 0 and curr_body / curr_range > 0.5
        return falling and strong_bull

    def _three_bar_reversal_bear(self) -> bool:
        """Three rising closes then a strong bearish bar."""
        if len(self._candles) < 4:
            return False
        c3 = self._candles[-4]
        c2 = self._candles[-3]
        c1 = self._candles[-2]
        c0 = self._candles[-1]
        rising = c2[3] > c3[3] and c1[3] > c2[3]
        curr_body = c0[0] - c0[3]
        curr_range = c0[1] - c0[2]
        strong_bear = curr_body > 0 and curr_range > 0 and curr_body / curr_range > 0.5
        return rising and strong_bear

    def _volume_score(self, features: FeatureVector, direction: Direction) -> int:
        """Score volume conditions (0-2 points).
        High volume at extremes = exhaustion = reversal signal.
        """
        score = 0
        # Volume spike (exhaustion)
        if features.volume_ratio >= 2.0:
            score += 2  # Very high volume = strong exhaustion
        elif features.volume_ratio >= 1.5:
            score += 1
        return score

    def _liquidation_score(self, features: FeatureVector, direction: Direction) -> int:
        """Score liquidation proximity (0-2 points).
        Price near liquidation cluster = likely bounce.
        """
        score = 0
        price = features.price
        liq_above = features.liquidation_above
        liq_below = features.liquidation_below

        if direction == Direction.LONG:
            # Price near lower liquidation zone = shorts getting squeezed
            if liq_below > 0:
                dist_pct = (price - liq_below) / price
                if dist_pct < 0.005:  # Within 0.5%
                    score += 2
                elif dist_pct < 0.015:  # Within 1.5%
                    score += 1
        else:
            # Price near upper liquidation zone
            if liq_above > 0:
                dist_pct = (liq_above - price) / price
                if dist_pct < 0.005:
                    score += 2
                elif dist_pct < 0.015:
                    score += 1
        return score

    def generate_signal(self, features: FeatureVector) -> Optional[Signal]:
        price = features.price
        volume = features.volume_ratio
        self._bar_count += 1

        # Build estimated candle
        o, h, l, c = self._estimate_candle(price, volume)
        self._candles.append((o, h, l, c, volume))
        self._prev_price = price

        if len(self._candles) < 5:
            return None

        # Cooldown
        if self._bar_count - self._last_signal_bar < self._cooldown_bars:
            return None

        # Regime filter: only trade reversals
        allowed_long = features.regime_label in (RegimeLabel.TREND_DOWN, RegimeLabel.RANGE)
        allowed_short = features.regime_label in (RegimeLabel.TREND_UP, RegimeLabel.RANGE)

        for direction in [Direction.LONG, Direction.SHORT]:
            if direction == Direction.LONG and not allowed_long:
                continue
            if direction == Direction.SHORT and not allowed_short:
                continue

            # --- Candlestick score (0-2) ---
            candle_score = 0
            pattern = ""
            if direction == Direction.LONG:
                if self._is_bullish_engulfing():
                    candle_score = 2
                    pattern = "ENGULF"
                elif self._is_bullish_pin_bar():
                    candle_score = 2
                    pattern = "PIN"
                elif self._three_bar_reversal_bull():
                    candle_score = 1
                    pattern = "3BAR"
            else:
                if self._is_bearish_engulfing():
                    candle_score = 2
                    pattern = "ENGULF"
                elif self._is_bearish_pin_bar():
                    candle_score = 2
                    pattern = "PIN"
                elif self._three_bar_reversal_bear():
                    candle_score = 1
                    pattern = "3BAR"

            if candle_score == 0:
                continue  # Must have at least a candle pattern

            # --- Volume score (0-2) ---
            vol_score = self._volume_score(features, direction)

            # --- Liquidation score (0-2) ---
            liq_score = self._liquidation_score(features, direction)

            total_score = candle_score + vol_score + liq_score

            if total_score >= self._min_score:
                self._last_signal_bar = self._bar_count
                strength = min(total_score / 6.0, 1.0)
                strength = max(strength, 0.3)

                signal = Signal(
                    symbol=self._symbol,
                    direction=direction,
                    strength=strength,
                    timestamp=int(time.time()),
                )
                logger.info("CANDLE_VOL %s score=%d/6 pattern=%s vol=%.2f liq=%d regime=%s",
                            direction.value, total_score, pattern,
                            features.volume_ratio, liq_score,
                            features.regime_label.value)
                return signal

        return None
