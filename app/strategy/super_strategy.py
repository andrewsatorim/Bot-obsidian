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

    Scoring: need score >= min_score out of 5 factors to enter.
    Gates: regime, volatility, volume, cooldown, spread.
    """

    def __init__(
        self,
        symbol: str = "BTC/USDT:USDT",
        bb_period: int = 20,
        cooldown_bars: int = 12,   # 12 hours on 1h TF
        min_score: int = 4,        # Need 4/5 factors (stricter)
    ) -> None:
        self._symbol = symbol
        self._bb_period = bb_period
        self._cooldown_bars = cooldown_bars
        self._min_score = min_score
        self._bars_since_signal = 999
        self._price_buffer: deque[float] = deque(maxlen=bb_period * 2)

    def generate_signal(self, features: FeatureVector) -> Optional[Signal]:
        self._bars_since_signal += 1
        price = features.price
        atr = features.atr

        if price == 0 or atr == 0:
            return None

        self._price_buffer.append(price)

        # === GATES (all must pass) ===
        if self._bars_since_signal < self._cooldown_bars:
            return None
        if features.regime_label not in (RegimeLabel.TREND_UP, RegimeLabel.TREND_DOWN):
            return None
        if features.volatility_regime > 0.05:
            return None
        if features.volume_ratio < 1.3:
            return None

        # === SCORING ===
        score = 0
        direction: Optional[Direction] = None

        # Factor 1: Trend direction
        if features.regime_label == RegimeLabel.TREND_UP:
            direction = Direction.LONG
            score += 1
        elif features.regime_label == RegimeLabel.TREND_DOWN:
            direction = Direction.SHORT
            score += 1

        if direction is None:
            return None

        # Factor 2: OI confirmation or divergence
        if features.oi_trend > 0.01:
            score += 1
        elif features.oi_trend < -0.02 and features.oi_delta < 0:
            direction = Direction.SHORT if direction == Direction.LONG else Direction.LONG
            score += 1

        # Factor 3: Funding alignment
        if direction == Direction.LONG and features.funding_zscore < -0.5:
            score += 1
        elif direction == Direction.SHORT and features.funding_zscore > 0.5:
            score += 1

        # Factor 4: Bollinger timing
        if len(self._price_buffer) >= self._bb_period:
            window = list(self._price_buffer)[-self._bb_period:]
            sma = mean(window)
            std = pstdev(window)
            if std > 0:
                if direction == Direction.LONG and price < sma - std:
                    score += 1
                elif direction == Direction.SHORT and price > sma + std:
                    score += 1

        # Factor 5: Liquidation proximity
        if features.liquidation_above > 0 and features.liquidation_below > 0:
            dist_above = (features.liquidation_above - price) / price
            dist_below = (price - features.liquidation_below) / price
            if direction == Direction.LONG and dist_below < 0.01:
                return None
            if direction == Direction.SHORT and dist_above < 0.01:
                return None
            if direction == Direction.LONG and dist_above < 0.03:
                score += 1
            elif direction == Direction.SHORT and dist_below < 0.03:
                score += 1

        # === MIN SCORE ===
        if score < self._min_score:
            return None

        spread_pct = features.spread / price if price > 0 else 0
        if spread_pct > 0.0005:
            return None

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
