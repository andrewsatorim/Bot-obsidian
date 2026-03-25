from __future__ import annotations

import math
import random
import time
from collections import deque

from app.models.market_data_bundle import MarketDataBundle
from app.models.market_snapshot import MarketSnapshot
from app.ports.data_feed_port import DataFeedPort

HISTORY_SIZE = 100


class SimulatedDataFeed(DataFeedPort):
    """Data feed with random-walk prices and sinusoidal funding for testing."""

    def __init__(self, start_price: float = 65_000.0, volatility: float = 0.002) -> None:
        self._price = start_price
        self._volatility = volatility
        self._tick = 0

        self._price_history: deque[float] = deque(maxlen=HISTORY_SIZE)
        self._volume_history: deque[float] = deque(maxlen=HISTORY_SIZE)
        self._oi_history: deque[float] = deque(maxlen=HISTORY_SIZE)
        self._funding_history: deque[float] = deque(maxlen=HISTORY_SIZE)

        # Seed initial history
        for _ in range(20):
            self._advance()

    def _advance(self) -> None:
        self._tick += 1
        change = random.gauss(0, self._volatility) * self._price
        self._price = max(self._price + change, 1.0)
        self._price_history.append(self._price)

        volume = random.uniform(500, 2000)
        self._volume_history.append(volume)

        oi = 50_000 + random.gauss(0, 1000)
        self._oi_history.append(oi)

        # Sinusoidal funding to trigger mean-reversion strategy
        funding = 0.0005 * math.sin(self._tick / 15.0) + random.gauss(0, 0.0001)
        self._funding_history.append(funding)

    async def get_market_data(self, symbol: str) -> MarketDataBundle:
        self._advance()

        spread = self._price * 0.0002
        snapshot = MarketSnapshot(
            symbol=symbol,
            price=self._price,
            volume=self._volume_history[-1],
            bid=self._price - spread / 2,
            ask=self._price + spread / 2,
            timestamp=int(time.time()),
        )

        return MarketDataBundle(
            market=snapshot,
            price_history=list(self._price_history),
            volume_history=list(self._volume_history),
            oi_history=list(self._oi_history),
            funding_history=list(self._funding_history),
        )
