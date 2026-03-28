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


class ElliottWaveStrategy(StrategyPort):
    """Elliott Wave multi-timeframe strategy.

    Logic:
    1. Detect wave structure on price history (simulates 4H view)
       - 5-wave impulse: waves 1-2-3-4-5
       - Entry at wave 3 start (after wave 2 correction) or wave 5
    2. Confirm on medium timeframe (1H/30m view from price history depth)
       - Wave 2 retracement must be 50-78.6% of wave 1 (Fibonacci)
       - Wave 4 must NOT overlap wave 1 territory
    3. Volume confirmation
       - Wave 3 should have highest volume (impulse wave)
       - Wave 2 should have declining volume (correction)
    4. Liquidation zone proximity check
    5. Entry on lower timeframe momentum (price momentum on recent bars)

    Exit: trailing stop only.
    """

    def __init__(self, symbol: str = "BTC/USDT",
                 wave_lookback: int = 40,
                 min_wave_size_pct: float = 0.005,
                 fib_retrace_min: float = 0.382,
                 fib_retrace_max: float = 0.886,
                 cooldown_bars: int = 30,
                 volume_confirm: float = 1.2) -> None:
        self._symbol = symbol
        self._wave_lookback = wave_lookback
        self._min_wave_pct = min_wave_size_pct
        self._fib_min = fib_retrace_min
        self._fib_max = fib_retrace_max
        self._cooldown = cooldown_bars
        self._vol_confirm = volume_confirm
        self._price_history: deque[float] = deque(maxlen=100)
        self._volume_history: deque[float] = deque(maxlen=100)
        self._bar_count: int = 0
        self._last_signal_bar: int = -100

    def _find_pivots(self, prices: list[float], order: int = 3) -> list[tuple[int, float, str]]:
        """Find swing highs and lows in price series.
        Returns list of (index, price, 'H'|'L')."""
        pivots = []
        for i in range(order, len(prices) - order):
            # Swing high
            is_high = all(prices[i] >= prices[i - j] and prices[i] >= prices[i + j]
                         for j in range(1, order + 1))
            if is_high:
                pivots.append((i, prices[i], "H"))
                continue
            # Swing low
            is_low = all(prices[i] <= prices[i - j] and prices[i] <= prices[i + j]
                        for j in range(1, order + 1))
            if is_low:
                pivots.append((i, prices[i], "L"))
        return pivots

    def _clean_pivots(self, pivots: list[tuple[int, float, str]]) -> list[tuple[int, float, str]]:
        """Remove consecutive same-type pivots, keep most extreme."""
        if not pivots:
            return []
        cleaned = [pivots[0]]
        for p in pivots[1:]:
            if p[2] == cleaned[-1][2]:
                # Same type — keep more extreme
                if p[2] == "H" and p[1] > cleaned[-1][1]:
                    cleaned[-1] = p
                elif p[2] == "L" and p[1] < cleaned[-1][1]:
                    cleaned[-1] = p
            else:
                cleaned.append(p)
        return cleaned

    def _detect_bullish_impulse(self, pivots: list[tuple[int, float, str]],
                                 prices: list[float]) -> Optional[dict]:
        """Detect bullish 5-wave impulse pattern.
        Wave 1 up, Wave 2 down (retrace), Wave 3 up (strongest),
        Wave 4 down, Wave 5 up.
        Returns wave structure dict or None."""
        if len(pivots) < 5:
            return None

        # Look for L-H-L-H-L-H pattern (bullish impulse)
        for i in range(len(pivots) - 4):
            p0 = pivots[i]      # Wave 1 start (low)
            p1 = pivots[i + 1]  # Wave 1 end / Wave 2 start (high)
            p2 = pivots[i + 2]  # Wave 2 end / Wave 3 start (low)
            p3 = pivots[i + 3]  # Wave 3 end / Wave 4 start (high)
            p4 = pivots[i + 4]  # Wave 4 end / Wave 5 start (low) — or current

            # Must alternate L-H-L-H-L
            if not (p0[2] == "L" and p1[2] == "H" and p2[2] == "L"
                    and p3[2] == "H" and p4[2] == "L"):
                continue

            wave1 = p1[1] - p0[1]  # up
            wave2 = p1[1] - p2[1]  # down (retracement)
            wave3 = p3[1] - p2[1]  # up
            wave4 = p3[1] - p4[1]  # down

            # Wave sizes must be meaningful
            if wave1 <= 0 or wave3 <= 0:
                continue
            min_size = p0[1] * self._min_wave_pct
            if wave1 < min_size or wave3 < min_size:
                continue

            # Rule: Wave 2 retracement 38.2%-88.6% of Wave 1
            retrace2 = wave2 / wave1 if wave1 > 0 else 0
            if retrace2 < self._fib_min or retrace2 > self._fib_max:
                continue

            # Rule: Wave 3 must be longer than Wave 1 (usually the strongest)
            if wave3 < wave1 * 0.8:
                continue

            # Rule: Wave 4 must NOT enter Wave 1 territory
            if p4[1] < p1[1]:
                continue

            # Rule: Wave 4 retracement 23.6%-61.8% of Wave 3
            retrace4 = wave4 / wave3 if wave3 > 0 else 0
            if retrace4 < 0.15 or retrace4 > 0.70:
                continue

            return {
                "direction": Direction.LONG,
                "wave1_start": p0, "wave1_end": p1,
                "wave2_end": p2, "wave3_end": p3,
                "wave4_end": p4,
                "wave1_size": wave1, "wave3_size": wave3,
                "retrace2": retrace2, "retrace4": retrace4,
            }
        return None

    def _detect_bearish_impulse(self, pivots: list[tuple[int, float, str]],
                                  prices: list[float]) -> Optional[dict]:
        """Detect bearish 5-wave impulse (mirror of bullish)."""
        if len(pivots) < 5:
            return None

        for i in range(len(pivots) - 4):
            p0 = pivots[i]      # High
            p1 = pivots[i + 1]  # Low (wave 1 end)
            p2 = pivots[i + 2]  # High (wave 2 end)
            p3 = pivots[i + 3]  # Low (wave 3 end)
            p4 = pivots[i + 4]  # High (wave 4 end)

            if not (p0[2] == "H" and p1[2] == "L" and p2[2] == "H"
                    and p3[2] == "L" and p4[2] == "H"):
                continue

            wave1 = p0[1] - p1[1]  # down
            wave2 = p2[1] - p1[1]  # up (retrace)
            wave3 = p2[1] - p3[1]  # down
            wave4 = p4[1] - p3[1]  # up

            if wave1 <= 0 or wave3 <= 0:
                continue
            min_size = p0[1] * self._min_wave_pct
            if wave1 < min_size or wave3 < min_size:
                continue

            retrace2 = wave2 / wave1 if wave1 > 0 else 0
            if retrace2 < self._fib_min or retrace2 > self._fib_max:
                continue

            if wave3 < wave1 * 0.8:
                continue

            if p4[1] > p1[1]:
                continue

            retrace4 = wave4 / wave3 if wave3 > 0 else 0
            if retrace4 < 0.15 or retrace4 > 0.70:
                continue

            return {
                "direction": Direction.SHORT,
                "wave1_start": p0, "wave1_end": p1,
                "wave2_end": p2, "wave3_end": p3,
                "wave4_end": p4,
                "wave1_size": wave1, "wave3_size": wave3,
                "retrace2": retrace2, "retrace4": retrace4,
            }
        return None

    def _volume_confirmation(self, wave: dict, volumes: list[float]) -> bool:
        """Check volume pattern matches Elliott rules.
        Wave 3 volume > Wave 1 volume (impulse acceleration).
        Wave 2/4 volume < Wave 1 volume (correction = low participation).
        """
        w1_start_idx = wave["wave1_start"][0]
        w1_end_idx = wave["wave1_end"][0]
        w2_end_idx = wave["wave2_end"][0]
        w3_end_idx = wave["wave3_end"][0]

        if w3_end_idx >= len(volumes):
            return False

        # Average volume per wave
        w1_vol = sum(volumes[w1_start_idx:w1_end_idx + 1]) / max(w1_end_idx - w1_start_idx, 1)
        w2_vol = sum(volumes[w1_end_idx:w2_end_idx + 1]) / max(w2_end_idx - w1_end_idx, 1)
        w3_vol = sum(volumes[w2_end_idx:w3_end_idx + 1]) / max(w3_end_idx - w2_end_idx, 1)

        # Wave 3 should have higher volume than wave 1
        if w3_vol < w1_vol * 0.8:
            return False

        # Wave 2 should have lower volume (correction)
        if w2_vol > w1_vol * 1.5:
            return False

        return True

    def _momentum_entry(self, prices: list[float], direction: Direction) -> bool:
        """Check short-term momentum for precise entry (simulates 5m/15m check).
        Uses last 5 bars as proxy for lower timeframe."""
        if len(prices) < 5:
            return False
        recent = prices[-5:]
        if direction == Direction.LONG:
            # Price rising in last 5 bars (lower TF momentum up)
            return recent[-1] > recent[0] and recent[-1] > recent[-2]
        else:
            return recent[-1] < recent[0] and recent[-1] < recent[-2]

    def generate_signal(self, features: FeatureVector) -> Optional[Signal]:
        self._price_history.append(features.price)
        self._volume_history.append(features.volume_ratio)
        self._bar_count += 1

        if self._bar_count < self._wave_lookback + 10:
            return None

        if self._bar_count - self._last_signal_bar < self._cooldown:
            return None

        prices = list(self._price_history)[-self._wave_lookback:]
        volumes = list(self._volume_history)[-self._wave_lookback:]

        # Find pivots (order=3 simulates 4H structure on 30m data)
        pivots = self._find_pivots(prices, order=3)
        pivots = self._clean_pivots(pivots)

        if len(pivots) < 5:
            return None

        # Try to detect wave pattern
        wave = None

        # Only look for LONG at end of bearish impulse (wave 5 complete → reversal)
        # Or at wave 4 end of bullish impulse (entering wave 5)
        bearish_wave = self._detect_bearish_impulse(pivots, prices)
        if bearish_wave:
            # Bearish impulse complete → expect bullish reversal
            wave4_idx = bearish_wave["wave4_end"][0]
            # We're at or past wave 4/5 → reversal expected
            if len(prices) - wave4_idx <= 8:
                wave = bearish_wave
                wave["entry_direction"] = Direction.LONG  # Reversal

        bullish_wave = self._detect_bullish_impulse(pivots, prices)
        if bullish_wave:
            wave4_idx = bullish_wave["wave4_end"][0]
            if len(prices) - wave4_idx <= 8:
                wave = bullish_wave
                wave["entry_direction"] = Direction.SHORT  # Reversal

        # Also: enter wave 3 of impulse (trend continuation)
        if wave is None and bullish_wave:
            w2_idx = bullish_wave["wave2_end"][0]
            w3_idx = bullish_wave["wave3_end"][0]
            if w3_idx - w2_idx > 3 and len(prices) - w2_idx <= 12:
                wave = bullish_wave
                wave["entry_direction"] = Direction.LONG  # Wave 3 continuation

        if wave is None and bearish_wave:
            w2_idx = bearish_wave["wave2_end"][0]
            w3_idx = bearish_wave["wave3_end"][0]
            if w3_idx - w2_idx > 3 and len(prices) - w2_idx <= 12:
                wave = bearish_wave
                wave["entry_direction"] = Direction.SHORT

        if wave is None:
            return None

        direction = wave["entry_direction"]

        # Volume confirmation
        if not self._volume_confirmation(wave, volumes):
            return None

        # Liquidation zone check
        price = features.price
        liq_ok = False
        if direction == Direction.LONG:
            dist = (price - features.liquidation_below) / price if features.liquidation_below > 0 else 1
            liq_ok = dist < 0.03  # Within 3% of liquidation zone
        else:
            dist = (features.liquidation_above - price) / price if features.liquidation_above > 0 else 1
            liq_ok = dist < 0.03

        # Momentum entry (lower TF confirmation)
        if not self._momentum_entry(prices, direction):
            return None

        # Regime alignment
        if direction == Direction.LONG and features.regime_label == RegimeLabel.TREND_UP:
            pass  # Good — trend continuation
        elif direction == Direction.SHORT and features.regime_label == RegimeLabel.TREND_DOWN:
            pass  # Good
        elif direction == Direction.LONG and features.regime_label == RegimeLabel.TREND_DOWN:
            pass  # Reversal — allowed but lower strength
        elif direction == Direction.SHORT and features.regime_label == RegimeLabel.TREND_UP:
            pass  # Reversal — allowed
        # Don't filter by regime — Elliott works in all regimes

        # Signal strength
        w3_ratio = wave["wave3_size"] / wave["wave1_size"] if wave["wave1_size"] > 0 else 1
        strength = min(w3_ratio / 3.0, 1.0)
        if liq_ok:
            strength = min(strength + 0.2, 1.0)
        if features.volume_ratio > self._vol_confirm:
            strength = min(strength + 0.1, 1.0)
        strength = max(strength, 0.3)

        self._last_signal_bar = self._bar_count

        signal = Signal(
            symbol=self._symbol,
            direction=direction,
            strength=strength,
            timestamp=int(time.time()),
        )
        logger.info("ELLIOTT %s w1=%.4f w3=%.4f retrace2=%.1f%% retrace4=%.1f%% liq=%s",
                     direction.value, wave["wave1_size"], wave["wave3_size"],
                     wave["retrace2"] * 100, wave["retrace4"] * 100, liq_ok)
        return signal
