from __future__ import annotations

import logging
import time
from statistics import mean, pstdev
from typing import Optional

from app.models.enums import Direction, RegimeLabel
from app.models.feature_vector import FeatureVector
from app.models.signal import Signal
from app.ports.strategy_port import StrategyPort

logger = logging.getLogger(__name__)

BB_PERIOD = 20
BB_STD_MULT = 2.0
MIN_SQUEEZE_WIDTH = 0.01  # Min band width as % of price


class BollingerMeanReversionStrategy(StrategyPort):
    """Mean-reversion strategy using Bollinger Bands.

    Logic:
    - Price touches/breaks lower band in non-trending market -> LONG
    - Price touches/breaks upper band in non-trending market -> SHORT
    - Band squeeze (narrow bands) followed by touch = stronger signal
    - Filters: skip in strong trends, skip if volatility is extreme

    Why it works in crypto:
    - Crypto spends ~65% of time in ranges
    - Retail traders chase breakouts, creating mean-reversion opportunity
    - Funding rate alignment confirms over-extension
    """

    def __init__(self, symbol: str = "BTC/USDT:USDT", period: int = BB_PERIOD) -> None:
        self._symbol = symbol
        self._period = period
        self._price_buffer: list[float] = []

    def generate_signal(self, features: FeatureVector) -> Optional[Signal]:
        # Skip strong trends — mean reversion fails in trends
        if features.regime_label in (RegimeLabel.TREND_UP, RegimeLabel.TREND_DOWN):
            return None

        price = features.price
        self._price_buffer.append(price)
        if len(self._price_buffer) > self._period * 2:
            self._price_buffer = self._price_buffer[-self._period * 2:]

        if len(self._price_buffer) < self._period:
            return None

        window = self._price_buffer[-self._period:]
        sma = mean(window)
        std = pstdev(window)

        if std == 0 or sma == 0:
            return None

        upper_band = sma + BB_STD_MULT * std
        lower_band = sma - BB_STD_MULT * std
        band_width = (upper_band - lower_band) / sma

        # Determine signal
        direction: Optional[Direction] = None

        if price <= lower_band:
            direction = Direction.LONG
        elif price >= upper_band:
            direction = Direction.SHORT
        else:
            return None

        # Band squeeze = bands were narrow before touch (stronger signal)
        squeeze_bonus = 0.0
        if band_width < MIN_SQUEEZE_WIDTH * 3:
            squeeze_bonus = 0.2

        # Funding alignment bonus
        funding_bonus = 0.0
        if direction == Direction.LONG and features.funding_zscore < -0.5:
            funding_bonus = 0.15  # Shorts paying = bullish
        elif direction == Direction.SHORT and features.funding_zscore > 0.5:
            funding_bonus = 0.15  # Longs paying = bearish

        # How far outside the band
        if direction == Direction.LONG:
            deviation = (lower_band - price) / std if std > 0 else 0
        else:
            deviation = (price - upper_band) / std if std > 0 else 0

        strength = min(0.4 + deviation * 0.15 + squeeze_bonus + funding_bonus, 1.0)
        strength = max(strength, 0.1)

        signal = Signal(
            symbol=self._symbol,
            direction=direction,
            strength=strength,
            timestamp=int(time.time()),
        )
        logger.info(
            "BB signal: %s strength=%.2f price=%.2f sma=%.2f upper=%.2f lower=%.2f width=%.4f",
            direction.value, strength, price, sma, upper_band, lower_band, band_width,
        )
        return signal
