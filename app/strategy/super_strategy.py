from __future__ import annotations

import logging
import time
from collections import deque
from statistics import mean, pstdev
from typing import Optional

from app.models.enums import Direction, RegimeLabel
from app.models.feature_vector import FeatureVector
from app.models.signal import Signal
from app.ports.strategy_port import StrategyPort

logger = logging.getLogger(__name__)


class SuperStrategy(StrategyPort):
    """Best-of-all-7 combined strategy.

    Takes the best filter from each strategy that showed edge:

    From Breakout (100% WR, +11.43%):  regime must be TREND + OI expanding
    From OI Divergence (PF 5.19):      OI divergence with funding alignment
    From TrendFollowing (+expectancy): trend confirmation + low volatility
    From Bollinger:                    Bollinger band proximity for timing
    From FundingMR:                    funding z-score extremes
    From LiqSqueeze:                   liquidation proximity awareness

    Key insight from all tests: FEWER trades = BETTER results.
    Target: 5-15 trades per month (not 40+)
    """

    def __init__(
        self,
        symbol: str = "BTC/USDT:USDT",
        bb_period: int = 20,
        cooldown_bars: int = 8,  # 4 hours on 30min TF
    ) -> None:
        self._symbol = symbol
        self._bb_period = bb_period
        self._cooldown_bars = cooldown_bars
        self._bars_since_signal = 999
        self._price_buffer: deque[float] = deque(maxlen=bb_period * 2)

    def generate_signal(self, features: FeatureVector) -> Optional[Signal]:
        self._bars_since_signal += 1
        price = features.price
        atr = features.atr

        if price == 0 or atr == 0:
            return None

        # Build BB buffer
        self._price_buffer.append(price)

        # ============================================================
        # GATE 1: Cooldown (from test results: less trades = more profit)
        # ============================================================
        if self._bars_since_signal < self._cooldown_bars:
            return None

        # ============================================================
        # GATE 2: Regime filter (from Breakout: only trade in trends)
        # ============================================================
        if features.regime_label not in (RegimeLabel.TREND_UP, RegimeLabel.TREND_DOWN):
            return None

        # ============================================================
        # GATE 3: Volatility filter (from TrendFollowing: skip chaos)
        # ============================================================
        if features.volatility_regime > 0.05:
            return None

        # ============================================================
        # GATE 4: Volume confirmation (from Breakout: money must confirm)
        # ============================================================
        if features.volume_ratio < 1.3:
            return None

        # ============================================================
        # SIGNAL GENERATION: Multi-factor scoring
        # Each factor adds to score. Need score >= 3 out of 5 to trade.
        # ============================================================
        score = 0
        direction: Optional[Direction] = None

        # Factor 1: Trend direction (from Breakout — follow the trend)
        if features.regime_label == RegimeLabel.TREND_UP:
            direction = Direction.LONG
            score += 1
        elif features.regime_label == RegimeLabel.TREND_DOWN:
            direction = Direction.SHORT
            score += 1

        if direction is None:
            return None

        # Factor 2: OI confirmation (from Breakout: OI expanding = new money)
        # OR OI divergence (from OI Divergence: OI dropping = weak move)
        if features.oi_trend > 0.01:
            # OI expanding — confirms the trend (Breakout logic)
            score += 1
        elif features.oi_trend < -0.02 and features.oi_delta < 0:
            # OI divergence — counter-trend opportunity
            # Flip direction (from OI Divergence)
            direction = Direction.SHORT if direction == Direction.LONG else Direction.LONG
            score += 1

        # Factor 3: Funding alignment (from FundingMR + OI Divergence)
        if direction == Direction.LONG and features.funding_zscore < -0.5:
            score += 1  # Shorts paying = bullish
        elif direction == Direction.SHORT and features.funding_zscore > 0.5:
            score += 1  # Longs paying = bearish

        # Factor 4: Bollinger timing (from Bollinger — enter near bands)
        if len(self._price_buffer) >= self._bb_period:
            window = list(self._price_buffer)[-self._bb_period:]
            sma = mean(window)
            std = pstdev(window)
            if std > 0:
                upper = sma + 2 * std
                lower = sma - 2 * std
                # Price near lower band + LONG = good entry
                if direction == Direction.LONG and price < sma - std:
                    score += 1
                # Price near upper band + SHORT = good entry
                elif direction == Direction.SHORT and price > sma + std:
                    score += 1

        # Factor 5: Liquidation awareness (from LiqSqueeze)
        if features.liquidation_above > 0 and features.liquidation_below > 0:
            dist_above = (features.liquidation_above - price) / price
            dist_below = (price - features.liquidation_below) / price
            # Don't enter if we're near OUR liquidation zone
            if direction == Direction.LONG and dist_below < 0.01:
                return None  # Too close to long liquidation
            if direction == Direction.SHORT and dist_above < 0.01:
                return None  # Too close to short liquidation
            # Bonus: entering toward enemy liquidation zone = cascade potential
            if direction == Direction.LONG and dist_above < 0.03:
                score += 1  # Short squeeze potential
            elif direction == Direction.SHORT and dist_below < 0.03:
                score += 1  # Long cascade potential

        # ============================================================
        # GATE 5: Minimum score (need 3+ out of 5 factors)
        # ============================================================
        if score < 3:
            return None

        # Spread filter (from analysis: skip illiquid moments)
        spread_pct = features.spread / price if price > 0 else 0
        if spread_pct > 0.0005:
            return None

        # Strength based on score
        strength = min(score / 5.0, 1.0)
        strength = max(strength, 0.5)

        self._bars_since_signal = 0

        signal = Signal(
            symbol=self._symbol,
            direction=direction,
            strength=strength,
            timestamp=int(time.time()),
        )
        logger.info(
            "SUPER: %s score=%d/5 str=%.2f regime=%s oi_t=%.4f vol=%.2f fund_z=%.2f",
            direction.value, score, strength, features.regime_label.value,
            features.oi_trend, features.volume_ratio, features.funding_zscore,
        )
        return signal
