"""Download historical OHLCV + funding data from OKX and run backtest.

Usage:
    pip install ccxt
    python scripts/okx_backtest.py

Downloads 1000 hourly candles, funding rate history, runs all strategies.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ccxt


def download_candles(
    exchange: ccxt.Exchange,
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "1h",
    limit: int = 1000,
) -> list[list]:
    """Download OHLCV candles from OKX using pagination."""
    print(f"Downloading {limit} candles for {symbol} ({timeframe})...")
    all_candles = []

    # OKX returns newest first by default; we paginate backwards
    # Start from now, go back in time
    end_ts = int(time.time() * 1000)

    while len(all_candles) < limit:
        batch_limit = min(300, limit - len(all_candles))  # OKX allows up to 300
        try:
            candles = exchange.fetch_ohlcv(
                symbol, timeframe, limit=batch_limit,
                params={"before": str(end_ts)} if all_candles else {},
            )
        except Exception as e:
            print(f"  fetch error: {e}, retrying...")
            time.sleep(1)
            try:
                candles = exchange.fetch_ohlcv(symbol, timeframe, limit=batch_limit)
            except Exception:
                break

        if not candles:
            break

        # Deduplicate and sort
        existing_ts = {c[0] for c in all_candles}
        new_candles = [c for c in candles if c[0] not in existing_ts]
        if not new_candles:
            break

        all_candles.extend(new_candles)
        # Move end_ts to oldest candle for next page
        end_ts = min(c[0] for c in new_candles)
        print(f"  fetched {len(all_candles)}/{limit} candles")
        time.sleep(0.3)

    # Sort chronologically
    all_candles.sort(key=lambda c: c[0])
    print(f"Total candles: {len(all_candles)}")
    return all_candles


def download_funding_history(
    exchange: ccxt.Exchange,
    symbol: str = "BTC/USDT:USDT",
) -> list[dict]:
    """Download as much funding rate history as possible."""
    print(f"Downloading funding rate history for {symbol}...")
    all_rates = []

    try:
        # Try paginated fetch
        since = int((time.time() - 90 * 86400) * 1000)  # 90 days back
        for _ in range(10):  # Max 10 pages
            rates = exchange.fetch_funding_rate_history(symbol, since=since, limit=100)
            if not rates:
                break
            all_rates.extend(rates)
            since = rates[-1].get("timestamp", 0) + 1
            time.sleep(0.3)
    except Exception as e:
        print(f"  paginated fetch failed: {e}")
        # Fallback: single fetch
        try:
            rates = exchange.fetch_funding_rate_history(symbol, limit=100)
            all_rates = rates
        except Exception as e2:
            print(f"  funding history not available: {e2}")

    print(f"Funding rates: {len(all_rates)}")
    return all_rates


def save_csv(candles: list[list], path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for c in candles:
            writer.writerow([int(c[0] / 1000), c[1], c[2], c[3], c[4], c[5]])
    print(f"Saved {len(candles)} candles to {path}")


def build_bundles(candles: list[list], funding_rates: list[dict]):
    """Convert raw data to MarketDataBundles for backtest."""
    from app.models.market_data_bundle import MarketDataBundle
    from app.models.market_snapshot import MarketSnapshot

    bundles = []
    history_size = 50

    # Build funding rate lookup: hour -> rate
    funding_map: dict[int, float] = {}
    for fr in funding_rates:
        ts_ms = fr.get("timestamp", 0)
        rate = float(fr.get("fundingRate", 0))
        hour_key = int(ts_ms / 1000) // 3600
        funding_map[hour_key] = rate

    # Build cumulative funding history for z-score calculation
    sorted_rates = sorted(funding_map.items())
    all_funding_values = [r for _, r in sorted_rates] if sorted_rates else [0.0]

    print(f"Building {len(candles) - history_size} bundles (history_size={history_size})...")
    print(f"Funding rate range: {min(all_funding_values):.6f} to {max(all_funding_values):.6f}")

    for i in range(history_size, len(candles)):
        c = candles[i]
        ts = int(c[0] / 1000)
        price = float(c[4])
        volume = float(c[5])
        spread = price * 0.0001

        snapshot = MarketSnapshot(
            symbol="BTC/USDT:USDT",
            price=price,
            volume=volume,
            bid=price - spread / 2,
            ask=price + spread / 2,
            timestamp=max(ts, 1),
        )

        start = max(0, i - history_size)
        price_history = [float(candles[j][4]) for j in range(start, i + 1)]
        volume_history = [float(candles[j][5]) for j in range(start, i + 1)]

        # OI history: approximate from volume changes
        oi_history = [float(candles[j][5]) * 0.1 for j in range(start, i + 1)]

        # Funding history: use all known rates up to this point
        # This gives the strategy enough data for z-score calculation
        candle_hour = ts // 3600
        funding_history = []
        for hour_key, rate in sorted_rates:
            if hour_key <= candle_hour:
                funding_history.append(rate)
        if not funding_history:
            funding_history = [0.0]

        bundles.append(MarketDataBundle(
            market=snapshot,
            price_history=price_history,
            volume_history=volume_history,
            oi_history=oi_history,
            funding_history=funding_history,
        ))

    print(f"Built {len(bundles)} bundles")
    return bundles


def run_backtest(bundles):
    from app.analytics.feature_engine import FeatureEngine
    from app.backtest.engine import BacktestEngine
    from app.config import Settings
    from app.risk.risk_manager import RiskManager
    from app.strategy.bollinger_reversion import BollingerMeanReversionStrategy
    from app.strategy.breakout import BreakoutStrategy
    from app.strategy.funding_mean_reversion import FundingMeanReversionStrategy
    from app.strategy.fusion import StrategyFusion
    from app.strategy.liquidation_squeeze import LiquidationSqueezeStrategy
    from app.strategy.oi_divergence import OIDivergenceStrategy
    from app.strategy.trend_following import TrendFollowingStrategy

    settings = Settings(account_equity=10_000.0, paper_trading=True)
    analytics = FeatureEngine()
    risk = RiskManager(settings)
    symbol = "BTC/USDT:USDT"

    strategies = {
        "BollingerReversion": BollingerMeanReversionStrategy(symbol=symbol),
        "OI Divergence": OIDivergenceStrategy(symbol=symbol),
        "LiquidationSqueeze": LiquidationSqueezeStrategy(symbol=symbol),
        "FundingMeanReversion": FundingMeanReversionStrategy(symbol=symbol),
        "Breakout": BreakoutStrategy(symbol=symbol),
        "TrendFollowing": TrendFollowingStrategy(symbol=symbol),
        "Fusion (all 6)": StrategyFusion(
            strategies=[
                (BollingerMeanReversionStrategy(symbol=symbol), 1.2),
                (OIDivergenceStrategy(symbol=symbol), 1.1),
                (LiquidationSqueezeStrategy(symbol=symbol), 1.0),
                (FundingMeanReversionStrategy(symbol=symbol), 0.9),
                (TrendFollowingStrategy(symbol=symbol), 0.8),
                (BreakoutStrategy(symbol=symbol), 0.7),
            ],
            min_agreement=1,
            min_strength=0.3,
        ),
    }

    print(f"\nRunning backtest on {len(bundles)} data points...\n")
    print("=" * 60)

    for name, strategy in strategies.items():
        engine = BacktestEngine(
            analytics=analytics,
            strategy=strategy,
            risk=risk,
            initial_equity=10_000.0,
        )
        result = engine.run(bundles)
        print(f"\n--- {name} ---")
        print(result.summary())
        print()

    print("=" * 60)


def main():
    exchange = ccxt.okx({"enableRateLimit": True})

    symbol = "BTC/USDT:USDT"

    # 1. Download data
    candles = download_candles(exchange, symbol, "1h", limit=1000)
    funding = download_funding_history(exchange, symbol)

    if len(candles) < 100:
        print(f"\nWARNING: Only {len(candles)} candles downloaded. Need 100+ for meaningful backtest.")
        print("Check if OKX API is accessible from this server.\n")

    # 2. Save raw data
    save_csv(candles, "data/okx_btc_1h.csv")
    os.makedirs("data", exist_ok=True)
    with open("data/okx_funding.json", "w") as f:
        json.dump(funding, f, indent=2, default=str)
    print(f"Saved funding data to data/okx_funding.json")

    # 3. Build bundles and run backtest
    bundles = build_bundles(candles, funding)
    if bundles:
        run_backtest(bundles)
    else:
        print("ERROR: No bundles built. Check data download.")


if __name__ == "__main__":
    main()
