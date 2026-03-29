"""News & Sentiment feeds for live trading.

Three FREE sources:
1. Alternative.me Fear & Greed Index (no API key)
2. CryptoPanic news + community votes (free tier)
3. Santiment social volume (free tier, optional)

Combined into a single news_score (-1.0 to +1.0).
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)


class NewsFeed:
    """Aggregates sentiment from multiple free sources."""

    def __init__(self, cryptopanic_key: str = "", santiment_key: str = "") -> None:
        self._cp_key = cryptopanic_key
        self._sant_key = santiment_key
        self._cache: dict[str, tuple[float, Any]] = {}  # key -> (timestamp, data)
        self._cache_ttl = 300  # 5 min cache

    def _cached_get(self, url: str, headers: dict | None = None, cache_key: str = "") -> dict:
        key = cache_key or url
        now = time.time()
        if key in self._cache and now - self._cache[key][0] < self._cache_ttl:
            return self._cache[key][1]
        try:
            r = requests.get(url, headers=headers, timeout=10)
            r.raise_for_status()
            data = r.json()
            self._cache[key] = (now, data)
            return data
        except Exception as e:
            logger.warning("News fetch failed [%s]: %s", key, e)
            return {}

    # ============ 1. FEAR & GREED INDEX ============

    def get_fear_greed(self) -> dict:
        """Get current Fear & Greed Index (0-100).

        0-24: Extreme Fear (buy signal)
        25-49: Fear
        50: Neutral
        51-74: Greed
        75-100: Extreme Greed (sell signal)

        FREE, no API key needed.
        """
        data = self._cached_get(
            "https://api.alternative.me/fng/?limit=1&format=json",
            cache_key="fng"
        )
        result = {"value": 50, "label": "Neutral", "signal": 0.0}
        fng = data.get("data", [{}])
        if fng:
            val = int(fng[0].get("value", 50))
            label = fng[0].get("value_classification", "Neutral")
            result["value"] = val
            result["label"] = label

            # Convert to signal: -1 (extreme fear/buy) to +1 (extreme greed/sell)
            # For LONG: low fear = good (contrarian), high greed = bad
            result["signal"] = (val - 50) / 50  # -1 to +1
        return result

    # ============ 2. CRYPTOPANIC NEWS ============

    def get_cryptopanic_news(self, symbol: str = "BTC", limit: int = 10) -> dict:
        """Get latest crypto news with community sentiment votes.

        FREE tier: basic news without sentiment labels.
        Votes (positive/negative) available on free tier.

        Returns:
            sentiment: -1.0 to +1.0 based on vote ratio
            news_count: number of recent articles
            top_title: most voted article title
        """
        result = {"sentiment": 0.0, "news_count": 0, "top_title": "", "articles": []}

        if not self._cp_key:
            return result

        data = self._cached_get(
            f"https://cryptopanic.com/api/v1/posts/"
            f"?auth_token={self._cp_key}&currencies={symbol}"
            f"&kind=news&public=true",
            cache_key=f"cp_{symbol}"
        )

        posts = data.get("results", [])
        if not posts:
            return result

        total_pos = 0
        total_neg = 0
        articles = []

        for post in posts[:limit]:
            votes = post.get("votes", {})
            pos = int(votes.get("positive", 0) or 0)
            neg = int(votes.get("negative", 0) or 0)
            total_pos += pos
            total_neg += neg
            articles.append({
                "title": post.get("title", ""),
                "source": post.get("source", {}).get("title", ""),
                "positive": pos,
                "negative": neg,
                "url": post.get("url", ""),
            })

        result["news_count"] = len(articles)
        result["articles"] = articles
        if articles:
            result["top_title"] = articles[0]["title"]

        # Sentiment from votes
        total = total_pos + total_neg
        if total > 0:
            result["sentiment"] = (total_pos - total_neg) / total  # -1 to +1
        return result

    # ============ 3. SANTIMENT (optional) ============

    def get_santiment_social(self, symbol: str = "bitcoin") -> dict:
        """Get social volume and sentiment from Santiment.

        FREE tier: limited but functional.
        Maps crypto symbol to Santiment slug.
        """
        result = {"social_volume": 0, "sentiment": 0.0}

        slug_map = {
            "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
            "ADA": "cardano", "XRP": "xrp", "DOGE": "dogecoin",
            "AVAX": "avalanche-2", "LINK": "chainlink", "DOT": "polkadot",
            "SUI": "sui",
        }
        slug = slug_map.get(symbol.upper(), symbol.lower())

        try:
            # Santiment free API — social volume
            data = self._cached_get(
                f"https://api.santiment.net/graphql",
                cache_key=f"sant_{symbol}"
            )
            # Note: Santiment uses GraphQL, basic REST not available
            # For now, return neutral — integrate GraphQL client later
        except Exception:
            pass

        return result

    # ============ COMBINED SCORE ============

    def get_news_score(self, symbol: str = "BTC") -> dict:
        """Get combined news/sentiment score from all sources.

        Returns:
            score: -1.0 (bearish) to +1.0 (bullish)
            fear_greed: 0-100
            news_sentiment: -1.0 to +1.0
            details: breakdown per source
        """
        # 1. Fear & Greed (weight: 40%)
        fng = self.get_fear_greed()
        fng_signal = fng["signal"]  # -1 to +1 (high greed = positive)

        # For trading: CONTRARIAN — extreme fear = bullish, extreme greed = bearish
        # Invert: fear (-1 from FNG) → bullish (+1 for us)
        contrarian_fng = -fng_signal

        # 2. CryptoPanic news (weight: 40%)
        cp = self.get_cryptopanic_news(symbol)
        cp_sentiment = cp["sentiment"]  # -1 to +1

        # 3. Santiment (weight: 20%)
        sant = self.get_santiment_social(symbol)
        sant_sentiment = sant["sentiment"]  # -1 to +1

        # Weighted combination
        if self._cp_key:
            score = contrarian_fng * 0.4 + cp_sentiment * 0.4 + sant_sentiment * 0.2
        else:
            score = contrarian_fng * 0.7 + sant_sentiment * 0.3

        score = max(min(score, 1.0), -1.0)

        result = {
            "score": score,
            "fear_greed": fng["value"],
            "fear_greed_label": fng["label"],
            "news_sentiment": cp_sentiment,
            "news_count": cp["news_count"],
            "top_headline": cp.get("top_title", ""),
            "details": {
                "fng_raw": fng_signal,
                "fng_contrarian": contrarian_fng,
                "cryptopanic": cp_sentiment,
                "santiment": sant_sentiment,
            }
        }

        logger.info("[%s] News: score=%.2f FnG=%d(%s) CP=%.2f(%d articles)",
                     symbol, score, fng["value"], fng["label"],
                     cp_sentiment, cp["news_count"])

        return result

    def should_skip_trade(self, symbol: str, direction: str) -> tuple[bool, str]:
        """Check if news sentiment is strongly against our direction.

        Returns (should_skip, reason).
        """
        news = self.get_news_score(symbol)
        score = news["score"]
        fng = news["fear_greed"]

        # Extreme Fear & Greed filter
        if direction == "LONG" and fng > 85:
            return True, f"Extreme Greed ({fng}) — risky for LONG"
        if direction == "SHORT" and fng < 15:
            return True, f"Extreme Fear ({fng}) — risky for SHORT"

        # Strong sentiment against direction
        if direction == "LONG" and score < -0.5:
            return True, f"Strong bearish sentiment ({score:.2f})"
        if direction == "SHORT" and score > 0.5:
            return True, f"Strong bullish sentiment ({score:.2f})"

        return False, ""
