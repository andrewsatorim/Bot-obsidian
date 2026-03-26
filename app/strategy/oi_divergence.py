from __future__ import annotations

import logging
import time
from typing import Optional

from app.models.enums import Direction, RegimeLabel
from app.models.feature_vector import FeatureVector
from app.models.signal import Signal
from app.ports.strategy_port import StrategyPort

logger = logging.getLogger(__name__)


class OIDivergenceStrategy(StrategyPort):
    """OI Divergence with full filter stack.

    Core: Price UP + OI DOWN = weak rally -> SHORT (and vice versa)

    Filters (ALL must pass):
    HIGH PRIORITY:
    1. OI trend strong (< -0.03)
    2. OI delta confirms (must be negative - OI dropping NOW)
    3. Liquidation proximity (skip if price within 1% of liq level)
    4. Spread filter (skip if spread > 0.05% of price)
    5. Volume confirmation (> 1.3x average)
    6. Regime must be TREND (not RANGE)
    MEDIUM PRIORITY:
    7. Volume spike (bool confirmation)
    8. Slippage filter (skip if slippage > 0.1%)
    9. Funding alignment
    10. Cooldown between signals
    11. Minimum strength threshold
    """

    def __init__(
        self,
        symbol: str = "BTC/USDT:USDT",
        oi_threshold: float = -0.03,
        min_volume_ratio: float = 1.3,
        min_strength: float = 0.5,
        max_volatility: float = 0.06,
        cooldown_bars: int = 6,
        inverse: bool = False,
        # New filters
        max_spread_pct: float = 0.0005,     # 0.05% max spread
        max_slippage_pct: float = 0.001,    # 0.1% max slippage
        liq_proximity_pct: float = 0.01,    # 1% from liquidation = danger
        require_volume_spike: bool = True,  # volume_spike must be True
        require_oi_delta_neg: bool = True,  # oi_delta must be < 0
    ) -> None:
        self._symbol = symbol
        self._oi_threshold = oi_threshold
        self._min_volume_ratio = min_volume_ratio
        self._min_strength = min_strength
        self._max_volatility = max_volatility
        self._cooldown_bars = cooldown_bars
        self._inverse = inverse
        self._max_spread_pct = max_spread_pct
        self._max_slippage_pct = max_slippage_pct
        self._liq_proximity_pct = liq_proximity_pct
        self._require_volume_spike = require_volume_spike
        self._require_oi_delta_neg = require_oi_delta_neg
        self._bars_since_signal = 999

    def generate_signal(self, features: FeatureVector) -> Optional[Signal]:
        self._bars_since_signal += 1

        price = features.price
        atr = features.atr
        if atr == 0 or price == 0:
            return None

        # === HIGH PRIORITY FILTERS ===

        # Filter 1: Strong OI trend divergence
        if features.oi_trend >= self._oi_threshold:
            return None

        # Filter 2: OI delta must be negative (OI dropping right now)
        if self._require_oi_delta_neg and features.oi_delta >= 0:
            return None

        # Filter 3: Regime — only clear trends
        if features.regime_label == RegimeLabel.TREND_UP:
            direction = Direction.SHORT
        elif features.regime_label == RegimeLabel.TREND_DOWN:
            direction = Direction.LONG
        else:
            return None

        # Filter 4: Liquidation proximity — don't enter near liq zones
        if features.liquidation_above > 0 and features.liquidation_below > 0:
            dist_above = abs(features.liquidation_above - price) / price
            dist_below = abs(price - features.liquidation_below) / price
            if direction == Direction.LONG and dist_below < self._liq_proximity_pct:
                return None  # Long near long-liq zone = dangerous
            if direction == Direction.SHORT and dist_above < self._liq_proximity_pct:
                return None  # Short near short-liq zone = dangerous

        # Filter 5: Spread filter — skip low liquidity
        spread_pct = features.spread / price if price > 0 else 0
        if spread_pct > self._max_spread_pct:
            return None

        # Filter 6: Volume confirmation
        if features.volume_ratio < self._min_volume_ratio:
            return None

        # === MEDIUM PRIORITY FILTERS ===

        # Filter 7: Volume spike (bool)
        if self._require_volume_spike and not features.volume_spike:
            return None

        # Filter 8: Slippage filter
        slippage_pct = features.slippage_estimate / price if price > 0 else 0
        if slippage_pct > self._max_slippage_pct:
            return None

        # Filter 9: Volatility cap
        if features.volatility_regime > self._max_volatility:
            return None

        # Filter 10: Cooldown
        if self._bars_since_signal < self._cooldown_bars:
            return None

        # Filter 11: Funding alignment
        if direction == Direction.SHORT and features.funding_zscore < 0:
            return None
        if direction == Direction.LONG and features.funding_zscore > 0:
            return None

        # Strength calculation
        oi_magnitude = abs(features.oi_trend)
        strength = min(0.4 + oi_magnitude * 5.0, 1.0)
        if features.volume_ratio > 1.5:
            strength = min(strength + 0.1, 1.0)
        if features.volume_spike:
            strength = min(strength + 0.05, 1.0)

        # Filter 12: Minimum strength
        if strength < self._min_strength:
            return None

        self._bars_since_signal = 0

        # Inverse mode
        if self._inverse:
            direction = Direction.SHORT if direction == Direction.LONG else Direction.LONG

        signal = Signal(
            symbol=self._symbol,
            direction=direction,
            strength=strength,
            timestamp=int(time.time()),
        )
        logger.info(
            "OI div: %s str=%.2f oi_t=%.4f oi_d=%.2f vol=%.2f sprd=%.5f fund_z=%.2f",
            direction.value, strength, features.oi_trend, features.oi_delta,
            features.volume_ratio, spread_pct, features.funding_zscore,
        )
        return signal
