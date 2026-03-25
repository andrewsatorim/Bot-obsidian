from __future__ import annotations

import logging
import time
from typing import Optional

from app.models.enums import Direction
from app.models.feature_vector import FeatureVector
from app.models.signal import Signal
from app.ports.strategy_port import StrategyPort

logger = logging.getLogger(__name__)


class LiquidationSqueezeStrategy(StrategyPort):
    """Detects and trades liquidation cascades.

    Logic:
    - When price approaches a dense liquidation level + volume spikes ->
      expect cascade and ride the momentum
    - Liquidation above current price + price rising + volume spike -> LONG
      (short squeezing upward)
    - Liquidation below current price + price falling + volume spike -> SHORT
      (long liquidation cascade downward)

    Why it works:
    - Liquidation cascades are self-reinforcing: each liquidation pushes price
      further, triggering more liquidations
    - ~30% of large crypto moves are driven by cascading liquidations
    - High R:R: cascades tend to be violent and fast
    - Works best on BTC/ETH perpetuals with high leverage
    """

    def __init__(
        self,
        symbol: str = "BTC/USDT:USDT",
        liq_proximity_pct: float = 0.02,  # How close price must be to liq level
        min_volume_ratio: float = 1.3,     # Min volume spike for confirmation
    ) -> None:
        self._symbol = symbol
        self._liq_proximity = liq_proximity_pct
        self._min_volume = min_volume_ratio

    def generate_signal(self, features: FeatureVector) -> Optional[Signal]:
        price = features.price
        liq_above = features.liquidation_above
        liq_below = features.liquidation_below

        if price <= 0:
            return None

        direction: Optional[Direction] = None
        liq_distance = 0.0

        # Check proximity to liquidation levels
        if liq_above > 0:
            dist_above = (liq_above - price) / price
            if dist_above <= self._liq_proximity and dist_above > 0:
                # Price approaching liquidation level above -> short squeeze
                direction = Direction.LONG
                liq_distance = dist_above

        if liq_below > 0 and direction is None:
            dist_below = (price - liq_below) / price
            if dist_below <= self._liq_proximity and dist_below > 0:
                # Price approaching liquidation level below -> long liquidation
                direction = Direction.SHORT
                liq_distance = dist_below

        if direction is None:
            return None

        # Volume confirmation — cascades require volume
        if features.volume_ratio < self._min_volume:
            return None

        # OI confirmation — during cascades OI typically drops sharply
        oi_dropping = features.oi_delta < 0

        # Funding confirmation
        funding_aligned = False
        if direction == Direction.LONG and features.funding_zscore > 0.5:
            # High funding = many longs paying -> shorts are crowded above
            funding_aligned = True
        elif direction == Direction.SHORT and features.funding_zscore < -0.5:
            funding_aligned = True

        # Strength calculation
        proximity_score = max(1.0 - (liq_distance / self._liq_proximity), 0)
        volume_score = min(features.volume_ratio / 3.0, 1.0)

        strength = 0.3 + proximity_score * 0.3 + volume_score * 0.2
        if oi_dropping:
            strength += 0.1
        if funding_aligned:
            strength += 0.1
        strength = max(min(strength, 1.0), 0.1)

        signal = Signal(
            symbol=self._symbol,
            direction=direction,
            strength=strength,
            timestamp=int(time.time()),
        )
        logger.info(
            "liquidation squeeze signal: %s strength=%.2f liq_dist=%.4f vol_ratio=%.2f oi_delta=%.2f",
            direction.value, strength, liq_distance, features.volume_ratio, features.oi_delta,
        )
        return signal
