"""Download historical OHLCV + funding data from OKX and run backtest.

Usage:
    pip install ccxt
    python scripts/okx_backtest.py

This will:
1. Download 1000 hourly candles from OKX BTC-USDT-SWAP
2. Download funding rate history
3. Run backtest with all 3 strategies
4. Print full metrics report
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ccxt


def download_candles(
    exchange: ccxt.Exchange,
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "1h",
    limit: int = 1000,
) -> list[list]:
    """Download OHLCV candles from OKX."""
    print(f"Downloading {limit} candles for {symbol} ({timeframe})...")
    all_candles = []
    since = None

    while len(all_candles) < limit:
        batch_limit = min(100, limit - len(all_candles))
        candles = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=batch_limit)
        if not candles:
            break
        all_candles.extend(candles)
        since = candles[-1][0] + 1
        print(f"  fetched {len(all_candles)}/{limit} candles")
        time.sleep(0.2)  # Rate limiting

    print(f"Total candles: {len(all_candles)}")
    return all_candles


def download_funding_history(
    exchange: ccxt.Exchange,
    symbol: str = "BTC/USDT:USDT",
    limit: int = 100,
) -> list[dict]:
    """Download funding rate history from OKX."""
    print(f"Downloading funding rate history for {symbol}...")
    try:
        rates = exchange.fetch_funding_rate_history(symbol, limit=limit)
        print(f"Funding rates: {len(rates)}")
        return rates
    except Exception as e:
        print(f"Funding rate history not available: {e}")
        return []


def save_csv(candles: list[list], path: str) -> None:
    """Save candles to CSV for HistoricalDataFeed."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for c in candles:
            writer.writerow([int(c[0] / 1000), c[1], c[2], c[3], c[4], c[5]])
    print(f"Saved to {path}")


def build_bundles(candles: list[list], funding_rates: list[dict]):
    """Convert raw data to MarketDataBundles for backtest."""
    from app.models.market_data_bundle import MarketDataBundle
    from app.models.market_snapshot import MarketSnapshot

    bundles = []
    history_size = 50

    # Build funding rate lookup by approximate timestamp
    funding_map: dict[int, float] = {}
    for fr in funding_rates:
        ts = int(fr.get("timestamp", 0) / 1000)
        rate = float(fr.get("fundingRate", 0))
        funding_map[ts // 3600] = rate

    for i in range(history_size, len(candles)):
        c = candles[i]
        ts = int(c[0] / 1000)
        price = float(c[4])  # close
        volume = float(c[5])
        spread = price * 0.0001

        snapshot = MarketSnapshot(
            symbol="BTC/USDT:USDT",
            price=price,
            volume=volume,
            bid=price - spread / 2,
            ask=price + spread / 2,
            timestamp=ts,
        )

        start = max(0, i - history_size)
        price_history = [float(candles[j][4]) for j in range(start, i + 1)]
        volume_history = [float(candles[j][5]) for j in range(start, i + 1)]

        # Approximate funding history from the window
        funding_history = []
        for j in range(start, i + 1):
            hour_key = int(candles[j][0] / 1000) // 3600
            if hour_key in funding_map:
                funding_history.append(funding_map[hour_key])

        bundles.append(MarketDataBundle(
            market=snapshot,
            price_history=price_history,
            volume_history=volume_history,
            funding_history=funding_history if funding_history else [0.0],
        ))

    return bundles


def run_backtest(bundles):
    """Run backtest with all strategies."""
    from app.analytics.feature_engine import FeatureEngine
    from app.backtest.engine import BacktestEngine
    from app.config import Settings
    from app.risk.risk_manager import RiskManager
    from app.strategy.breakout import BreakoutStrategy
    from app.strategy.funding_mean_reversion import FundingMeanReversionStrategy
    from app.strategy.fusion import StrategyFusion
    from app.strategy.trend_following import TrendFollowingStrategy

    settings = Settings(account_equity=10_000.0, paper_trading=True)
    analytics = FeatureEngine()
    risk = RiskManager(settings)
    symbol = "BTC/USDT:USDT"

    strategies = {
        "FundingMeanReversion": FundingMeanReversionStrategy(symbol=symbol),
        "Breakout": BreakoutStrategy(symbol=symbol),
        "TrendFollowing": TrendFollowingStrategy(symbol=symbol),
        "Fusion (all 3)": StrategyFusion(
            strategies=[
                (FundingMeanReversionStrategy(symbol=symbol), 1.0),
                (BreakoutStrategy(symbol=symbol), 0.8),
                (TrendFollowingStrategy(symbol=symbol), 0.7),
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
    # Initialize OKX exchange (no API key needed for public data)
    exchange = ccxt.okx({
        "enableRateLimit": True,
    })

    symbol = "BTC/USDT:USDT"

    # 1. Download data
    candles = download_candles(exchange, symbol, "1h", limit=1000)
    funding = download_funding_history(exchange, symbol, limit=100)

    # 2. Save to CSV
    save_csv(candles, "data/okx_btc_1h.csv")

    # 3. Save funding to JSON
    os.makedirs("data", exist_ok=True)
    with open("data/okx_funding.json", "w") as f:
        json.dump(funding, f, indent=2, default=str)
    print(f"Saved funding data to data/okx_funding.json")

    # 4. Build bundles and run backtest
    bundles = build_bundles(candles, funding)
    run_backtest(bundles)


if __name__ == "__main__":
    main()
