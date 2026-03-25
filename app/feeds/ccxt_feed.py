from __future__ import annotations

import logging
import time
from typing import Optional

import ccxt
import ccxt.async_support as ccxt_async

from app.models.market_data_bundle import MarketDataBundle
from app.models.market_snapshot import MarketSnapshot
from app.ports.data_feed_port import DataFeedPort

logger = logging.getLogger(__name__)

OHLCV_LIMIT = 100


class CcxtDataFeed(DataFeedPort):
    """Live data feed via ccxt (Binance, Bybit, etc.)."""

    def __init__(
        self,
        exchange_id: str,
        api_key: str = "",
        api_secret: str = "",
        passphrase: str = "",
    ) -> None:
        config: dict = {"enableRateLimit": True}
        if api_key:
            config["apiKey"] = api_key
            config["secret"] = api_secret
        if passphrase:
            config["password"] = passphrase  # OKX requires passphrase
        exchange_cls = getattr(ccxt_async, exchange_id, None)
        if exchange_cls is None:
            raise ValueError(f"Unknown exchange: {exchange_id}")
        self._exchange: ccxt_async.Exchange = exchange_cls(config)

    async def get_market_data(self, symbol: str) -> MarketDataBundle:
        ticker = await self._exchange.fetch_ticker(symbol)
        ohlcv = await self._exchange.fetch_ohlcv(symbol, timeframe="1m", limit=OHLCV_LIMIT)

        price = float(ticker.get("last", 0))
        volume = float(ticker.get("quoteVolume", 0) or ticker.get("baseVolume", 0) or 0)
        bid = float(ticker.get("bid", price))
        ask = float(ticker.get("ask", price))

        price_history = [float(c[4]) for c in ohlcv]  # close prices
        volume_history = [float(c[5]) for c in ohlcv]

        # Fetch funding rate if available (derivatives)
        funding_history: list[float] = []
        try:
            funding = await self._exchange.fetch_funding_rate(symbol)
            if funding and "fundingRate" in funding:
                funding_history = [float(funding["fundingRate"])]
        except Exception:
            logger.debug("funding rate not available for %s", symbol)

        # Fetch open interest if available
        oi_history: list[float] = []
        try:
            oi = await self._exchange.fetch_open_interest(symbol)
            if oi and "openInterestAmount" in oi:
                oi_history = [float(oi["openInterestAmount"])]
        except Exception:
            logger.debug("open interest not available for %s", symbol)

        snapshot = MarketSnapshot(
            symbol=symbol,
            price=max(price, 0.01),
            volume=max(volume, 0),
            bid=max(bid, 0),
            ask=max(ask, 0),
            timestamp=int(time.time()),
        )

        return MarketDataBundle(
            market=snapshot,
            price_history=price_history if price_history else [price],
            volume_history=volume_history if volume_history else [volume],
            oi_history=oi_history,
            funding_history=funding_history,
        )

    async def close(self) -> None:
        await self._exchange.close()
