from __future__ import annotations

import csv
import time
from pathlib import Path

from app.models.market_data_bundle import MarketDataBundle
from app.models.market_snapshot import MarketSnapshot
from app.ports.data_feed_port import DataFeedPort


class HistoricalDataFeed(DataFeedPort):
    """Replays historical OHLCV data from a CSV file for backtesting.

    CSV format: timestamp,open,high,low,close,volume
    """

    def __init__(self, csv_path: str, symbol: str = "BTC/USDT", history_size: int = 100) -> None:
        self._symbol = symbol
        self._history_size = history_size
        self._candles: list[dict] = []
        self._index = 0
        self._load_csv(csv_path)

    def _load_csv(self, path: str) -> None:
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                self._candles.append({
                    "timestamp": int(float(row.get("timestamp", 0))),
                    "open": float(row.get("open", 0)),
                    "high": float(row.get("high", 0)),
                    "low": float(row.get("low", 0)),
                    "close": float(row.get("close", 0)),
                    "volume": float(row.get("volume", 0)),
                })

    @property
    def total_candles(self) -> int:
        return len(self._candles)

    @property
    def current_index(self) -> int:
        return self._index

    def reset(self) -> None:
        self._index = 0

    async def get_market_data(self, symbol: str) -> MarketDataBundle:
        if self._index >= len(self._candles):
            raise StopIteration("No more historical data")

        candle = self._candles[self._index]
        self._index += 1

        start = max(0, self._index - self._history_size)
        history_slice = self._candles[start:self._index]

        price = candle["close"]
        spread = price * 0.0002

        snapshot = MarketSnapshot(
            symbol=self._symbol,
            price=price,
            volume=candle["volume"],
            bid=price - spread / 2,
            ask=price + spread / 2,
            timestamp=candle["timestamp"] or int(time.time()),
        )

        return MarketDataBundle(
            market=snapshot,
            price_history=[c["close"] for c in history_slice],
            volume_history=[c["volume"] for c in history_slice],
        )

    def to_bundles(self) -> list[MarketDataBundle]:
        """Convert all data to a list of MarketDataBundles for BacktestEngine."""
        bundles = []
        self.reset()
        while self._index < len(self._candles):
            import asyncio
            bundle = asyncio.get_event_loop().run_until_complete(
                self.get_market_data(self._symbol)
            )
            bundles.append(bundle)
        self.reset()
        return bundles
