"""Coinglass API integration for liquidation heatmap, OI, and funding data.

API docs: https://docs.coinglass.com/reference/introduction
Free tier: 30 req/min
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://open-api-v3.coinglass.com"


class CoinglassFeed:
    """Fetches liquidation heatmap, OI, long/short ratio from Coinglass."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._headers = {"accept": "application/json", "CG-API-KEY": api_key}

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{BASE_URL}{path}"
        resp = requests.get(url, headers=self._headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "0" and data.get("success") is not True:
            logger.warning("Coinglass API: %s", data.get("msg", "unknown error"))
        return data

    def get_liquidation_heatmap(self, symbol: str = "BTC", exchange: str = "OKX") -> dict:
        """Get liquidation levels aggregated.

        Returns approximate liquidation zones above and below current price.
        """
        try:
            data = self._get("/api/futures/liquidation/v2/order", {
                "symbol": symbol,
                "exchange": exchange,
            })
            return data.get("data", {})
        except Exception as e:
            logger.warning("Failed to fetch liquidation heatmap: %s", e)
            return {}

    def get_aggregated_oi(self, symbol: str = "BTC") -> dict:
        """Get Open Interest aggregated across all exchanges."""
        try:
            data = self._get("/api/futures/openInterest/chart", {
                "symbol": symbol,
                "interval": "30m",
                "limit": 500,
            })
            return data.get("data", {})
        except Exception as e:
            logger.warning("Failed to fetch aggregated OI: %s", e)
            return {}

    def get_oi_history(self, symbol: str = "BTC", interval: str = "30m", limit: int = 500) -> list[dict]:
        """Get OI history data points."""
        try:
            data = self._get("/api/futures/openInterest/ohlc-history", {
                "symbol": symbol,
                "interval": interval,
                "limit": str(limit),
            })
            records = data.get("data", [])
            if isinstance(records, list):
                return records
            return []
        except Exception as e:
            logger.warning("Failed to fetch OI history: %s", e)
            return []

    def get_long_short_ratio(self, symbol: str = "BTC", interval: str = "30m") -> dict:
        """Get long/short ratio (accounts and positions)."""
        try:
            data = self._get("/api/futures/globalLongShortAccountRatio/chart", {
                "symbol": symbol,
                "interval": interval,
                "limit": 500,
            })
            return data.get("data", {})
        except Exception as e:
            logger.warning("Failed to fetch long/short ratio: %s", e)
            return {}

    def get_funding_rates(self, symbol: str = "BTC") -> list[dict]:
        """Get funding rates across all exchanges."""
        try:
            data = self._get("/api/futures/funding/v2/current", {
                "symbol": symbol,
            })
            return data.get("data", [])
        except Exception as e:
            logger.warning("Failed to fetch funding rates: %s", e)
            return []

    def get_liquidation_levels(self, symbol: str = "BTC", price: float = 0) -> tuple[float, float]:
        """Get nearest liquidation levels above and below current price.

        Returns (liq_above, liq_below)
        """
        try:
            data = self._get("/api/futures/liquidation/v2/info", {
                "symbol": symbol,
            })
            info = data.get("data", {})

            # Extract liquidation volumes at price levels
            liq_above = price * 1.02  # Default: 2% above
            liq_below = price * 0.98  # Default: 2% below

            if isinstance(info, dict):
                # Look for concentration zones
                longs_liq = info.get("longVolUsd", 0)
                shorts_liq = info.get("shortVolUsd", 0)

                if longs_liq > shorts_liq * 1.5:
                    # More longs to liquidate -> price magnet below
                    liq_below = price * 0.985
                elif shorts_liq > longs_liq * 1.5:
                    # More shorts to liquidate -> price magnet above
                    liq_above = price * 1.015

            return liq_above, liq_below
        except Exception as e:
            logger.warning("Failed to fetch liquidation levels: %s", e)
            return price * 1.02, price * 0.98
