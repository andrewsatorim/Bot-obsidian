"""Coinglass V4 API — real-time OI, funding, L/S ratio for live trading.

Confirmed working endpoints on HOBBYIST plan ($29/mo):
- /api/futures/open-interest/exchange-list  (real-time OI)
- /api/futures/open-interest/history        (OI OHLC per exchange)
- /api/futures/funding-rate/exchange-list    (funding rates)
- /api/futures/supported-coins              (coin list)
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://open-api-v4.coinglass.com"


class CoinglassV4:
    """Coinglass V4 API client for live trading filters."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._headers = {"accept": "application/json", "CG-API-KEY": api_key}
        self._last_call = 0.0
        self._min_interval = 2.1  # 30 req/min = 2sec between calls

    def _get(self, path: str, params: dict | None = None) -> dict:
        # Rate limiting
        elapsed = time.time() - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.time()

        url = f"{BASE_URL}{path}"
        try:
            resp = requests.get(url, headers=self._headers, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != "0":
                logger.warning("Coinglass V4 error: %s — %s", path, data.get("msg", ""))
            return data
        except Exception as e:
            logger.error("Coinglass V4 request failed: %s — %s", path, e)
            return {"code": "-1", "msg": str(e), "data": None}

    # ============ OPEN INTEREST ============

    def get_oi_realtime(self, symbol: str = "BTC") -> dict:
        """Get real-time OI across all exchanges.

        Returns dict with:
        - open_interest_usd: total OI in USD
        - open_interest_change_percent_5m/15m/30m/1h/4h/24h
        - Per-exchange breakdown
        """
        data = self._get("/api/futures/open-interest/exchange-list", {"symbol": symbol})
        result = {"total": {}, "exchanges": []}
        if data.get("code") == "0" and data.get("data"):
            for item in data["data"]:
                if item.get("exchange") == "All":
                    result["total"] = {
                        "oi_usd": float(item.get("open_interest_usd", 0)),
                        "oi_qty": float(item.get("open_interest_quantity", 0)),
                        "change_5m": float(item.get("open_interest_change_percent_5m", 0)),
                        "change_15m": float(item.get("open_interest_change_percent_15m", 0)),
                        "change_30m": float(item.get("open_interest_change_percent_30m", 0)),
                        "change_1h": float(item.get("open_interest_change_percent_1h", 0)),
                        "change_4h": float(item.get("open_interest_change_percent_4h", 0)),
                        "change_24h": float(item.get("open_interest_change_percent_24h", 0)),
                    }
                else:
                    result["exchanges"].append({
                        "exchange": item.get("exchange"),
                        "oi_usd": float(item.get("open_interest_usd", 0)),
                    })
        return result

    def get_oi_expanding(self, symbol: str = "BTC") -> bool:
        """Check if OI is expanding (new money entering) — key filter for Breakout.

        Returns True if OI increased in last 30min AND 1h.
        """
        oi = self.get_oi_realtime(symbol)
        total = oi.get("total", {})
        change_30m = total.get("change_30m", 0)
        change_1h = total.get("change_1h", 0)
        return change_30m > 0 and change_1h > 0

    # ============ FUNDING RATE ============

    def get_funding_rates(self, symbol: str = "BTC") -> dict:
        """Get current funding rates across exchanges.

        Returns dict with average rate and per-exchange rates.
        """
        data = self._get("/api/futures/funding-rate/exchange-list", {"symbol": symbol})
        result = {"avg_rate": 0.0, "exchanges": []}
        if data.get("code") == "0" and data.get("data"):
            rates = []
            for item in data["data"]:
                rate = float(item.get("fundingRate", 0))
                result["exchanges"].append({
                    "exchange": item.get("exchange"),
                    "rate": rate,
                    "next_time": int(item.get("nextFundingTime", 0)),
                })
                rates.append(rate)
            if rates:
                result["avg_rate"] = sum(rates) / len(rates)
        return result

    def is_funding_extreme(self, symbol: str = "BTC", threshold: float = 0.0005) -> tuple[bool, float]:
        """Check if funding rate is extreme (potential reversal signal).

        Returns (is_extreme, avg_rate).
        |rate| > 0.05% = extreme.
        """
        fr = self.get_funding_rates(symbol)
        avg = fr.get("avg_rate", 0)
        return abs(avg) > threshold, avg

    # ============ LONG/SHORT RATIO ============

    def get_ls_ratio(self, symbol: str = "BTC", exchange: str = "Binance") -> dict:
        """Get global long/short account ratio.

        Returns latest ratio data.
        """
        data = self._get("/api/futures/global-long-short-account-ratio/history", {
            "exchange": exchange, "symbol": symbol,
            "interval": "1h", "limit": "1",
        })
        result = {"long_pct": 50.0, "short_pct": 50.0, "ratio": 1.0}
        if data.get("code") == "0" and data.get("data"):
            latest = data["data"][-1] if data["data"] else {}
            long_ratio = float(latest.get("longAccountRatio", 0.5))
            short_ratio = float(latest.get("shortAccountRatio", 0.5))
            result = {
                "long_pct": long_ratio * 100,
                "short_pct": short_ratio * 100,
                "ratio": long_ratio / short_ratio if short_ratio > 0 else 1.0,
            }
        return result

    def is_ls_skewed(self, symbol: str = "BTC", threshold: float = 65.0) -> tuple[bool, str]:
        """Check if L/S ratio is dangerously skewed.

        Returns (is_skewed, dominant_side).
        > 65% on one side = crowded trade.
        """
        ls = self.get_ls_ratio(symbol)
        if ls["long_pct"] > threshold:
            return True, "LONG"
        elif ls["short_pct"] > threshold:
            return True, "SHORT"
        return False, "NEUTRAL"

    # ============ LIQUIDATION HEATMAP ============

    def get_liquidation_heatmap(self, symbol: str = "BTC") -> dict:
        """Get liquidation data — aggregated long/short liquidation volumes.

        Shows where liquidation clusters are (price magnets).
        Returns:
            longs_liq_usd: total long liquidation volume
            shorts_liq_usd: total short liquidation volume
            dominant: which side has more liquidations pending
        """
        data = self._get("/api/futures/liquidation/detail", {"symbol": symbol})
        result = {
            "longs_liq_usd": 0.0,
            "shorts_liq_usd": 0.0,
            "dominant": "NEUTRAL",
            "liq_ratio": 1.0,
        }
        if data.get("code") == "0" and data.get("data"):
            info = data["data"]
            if isinstance(info, dict):
                longs = float(info.get("longVolUsd", 0) or 0)
                shorts = float(info.get("shortVolUsd", 0) or 0)
                result["longs_liq_usd"] = longs
                result["shorts_liq_usd"] = shorts
                if longs + shorts > 0:
                    result["liq_ratio"] = longs / (longs + shorts) if (longs + shorts) > 0 else 0.5
                if longs > shorts * 1.5:
                    result["dominant"] = "LONGS"  # more longs to liquidate = bearish pressure
                elif shorts > longs * 1.5:
                    result["dominant"] = "SHORTS"  # more shorts to liquidate = bullish pressure
        return result

    def get_liquidation_history(self, symbol: str = "BTC", interval: str = "h1") -> list[dict]:
        """Get recent liquidation events."""
        data = self._get("/api/futures/liquidation/history", {
            "symbol": symbol, "interval": interval, "limit": "24",
        })
        result = []
        if data.get("code") == "0" and data.get("data"):
            for item in data["data"]:
                result.append({
                    "time": int(item.get("time", 0)),
                    "long_vol": float(item.get("longVolUsd", 0) or 0),
                    "short_vol": float(item.get("shortVolUsd", 0) or 0),
                    "count": int(item.get("count", 0) or 0),
                })
        return result

    def get_liquidation_signal(self, symbol: str = "BTC") -> dict:
        """Analyze liquidation heatmap for trading signal.

        Logic:
        - If massive shorts are about to be liquidated above price = bullish (short squeeze)
        - If massive longs are about to be liquidated below price = bearish (long cascade)
        - Recent spike in liquidations = volatility incoming

        Returns:
            signal: 'BULLISH', 'BEARISH', or 'NEUTRAL'
            strength: 0.0 to 1.0
            reason: explanation
        """
        heatmap = self.get_liquidation_heatmap(symbol)
        history = self.get_liquidation_history(symbol)

        signal = "NEUTRAL"
        strength = 0.0
        reason = ""

        # Heatmap analysis
        liq_ratio = heatmap.get("liq_ratio", 0.5)
        dominant = heatmap.get("dominant", "NEUTRAL")

        if dominant == "SHORTS":
            # More shorts pending liquidation = potential short squeeze = BULLISH
            signal = "BULLISH"
            strength = min((heatmap["shorts_liq_usd"] / max(heatmap["longs_liq_usd"], 1) - 1) / 2, 1.0)
            reason = f"Short squeeze potential: {heatmap['shorts_liq_usd']/1e6:.0f}M shorts vs {heatmap['longs_liq_usd']/1e6:.0f}M longs"
        elif dominant == "LONGS":
            # More longs pending liquidation = potential long cascade = BEARISH
            signal = "BEARISH"
            strength = min((heatmap["longs_liq_usd"] / max(heatmap["shorts_liq_usd"], 1) - 1) / 2, 1.0)
            reason = f"Long cascade risk: {heatmap['longs_liq_usd']/1e6:.0f}M longs vs {heatmap['shorts_liq_usd']/1e6:.0f}M shorts"

        # Recent liquidation spike analysis
        if history and len(history) >= 2:
            recent_total = sum(h["long_vol"] + h["short_vol"] for h in history[-3:])
            older_total = sum(h["long_vol"] + h["short_vol"] for h in history[:-3]) / max(len(history) - 3, 1) * 3
            if older_total > 0 and recent_total > older_total * 2:
                strength = min(strength + 0.3, 1.0)
                reason += " | Liquidation spike detected"

        return {"signal": signal, "strength": strength, "reason": reason}

    # ============ COMBINED FILTER ============

    def check_entry_filters(self, symbol: str, direction: str) -> tuple[bool, list[str]]:
        """Run all Coinglass filters for entry decision.

        Args:
            symbol: e.g. "BTC"
            direction: "LONG" or "SHORT"

        Returns:
            (pass_all, reasons) — True if all filters pass.
        """
        reasons = []

        # Filter 1: OI must be expanding
        oi_expanding = self.get_oi_expanding(symbol)
        if not oi_expanding:
            reasons.append("OI_NOT_EXPANDING")

        # Filter 2: Funding not extreme against direction
        is_extreme, avg_rate = self.is_funding_extreme(symbol)
        if is_extreme:
            if direction == "LONG" and avg_rate > 0:
                reasons.append(f"FUNDING_HIGH({avg_rate:.4f})")
            elif direction == "SHORT" and avg_rate < 0:
                reasons.append(f"FUNDING_LOW({avg_rate:.4f})")

        # Filter 3: L/S ratio not crowded in our direction
        is_skewed, dominant = self.is_ls_skewed(symbol)
        if is_skewed and dominant == direction:
            reasons.append(f"LS_CROWDED({dominant})")

        # Filter 4: Liquidation heatmap not against our direction
        liq = self.get_liquidation_signal(symbol)
        if liq["strength"] > 0.3:
            if direction == "LONG" and liq["signal"] == "BEARISH":
                reasons.append(f"LIQ_BEARISH({liq['reason'][:40]})")
            elif direction == "SHORT" and liq["signal"] == "BULLISH":
                reasons.append(f"LIQ_BULLISH({liq['reason'][:40]})")

        passed = len(reasons) == 0
        return passed, reasons

    # ============ UTILITY ============

    def get_supported_coins(self) -> list[str]:
        """Get list of supported coins."""
        data = self._get("/api/futures/supported-coins")
        if data.get("code") == "0":
            return data.get("data", [])
        return []
