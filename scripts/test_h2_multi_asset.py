"""H2 Aggressive test: 30x leverage, BTC + top-10 altcoins.

Tests Quantum-Fractal hypothesis on:
  BTC, ETH, SOL, XRP, DOGE, ADA, AVAX, LINK, DOT, MATIC
  Timeframe: 30min
  Leverage: 30x

Usage:
    python scripts/test_h2_multi_asset.py
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Top-10 perp symbols on OKX
SYMBOLS = [
    "BTC/USDT:USDT",
]

LEVERAGE = 30
MARGIN_PCT = 0.07  # 7% of capital per trade
TIMEFRAME = "30m"
CANDLE_LIMIT = 1500  # ~31 days of 30min candles (48 per day × 31)


def download_candles(exchange, symbol: str, timeframe: str, limit: int) -> list[list]:
    """Download OHLCV candles with proper OKX pagination (going back in time)."""
    all_candles = []

    # First fetch — latest candles
    try:
        candles = exchange.fetch_ohlcv(symbol, timeframe, limit=min(300, limit))
    except Exception as e:
        print(f"    error: {e}")
        return []

    if not candles:
        return []
    all_candles.extend(candles)
    print(f"  {len(all_candles)}", end="", flush=True)

    # Paginate backwards using 'since' with oldest timestamp minus 1
    while len(all_candles) < limit:
        oldest_ts = min(c[0] for c in all_candles)
        # Go further back: fetch candles BEFORE the oldest we have
        # OKX: use 'after' param (returns candles older than this timestamp)
        try:
            batch = exchange.fetch_ohlcv(
                symbol, timeframe, limit=300,
                params={"after": str(oldest_ts)},
            )
        except Exception as e:
            print(f" err:{e}", end="")
            break

        if not batch:
            break

        existing = {c[0] for c in all_candles}
        new = [c for c in batch if c[0] not in existing]
        if not new:
            break

        all_candles.extend(new)
        print(f"..{len(all_candles)}", end="", flush=True)
        time.sleep(0.3)

    all_candles.sort(key=lambda c: c[0])
    print(f" total={len(all_candles)}")
    return all_candles


def download_funding(exchange, symbol: str) -> list[dict]:
    """Download funding rate history."""
    try:
        since = int((time.time() - 90 * 86400) * 1000)
        all_rates = []
        for _ in range(5):
            rates = exchange.fetch_funding_rate_history(symbol, since=since, limit=100)
            if not rates:
                break
            all_rates.extend(rates)
            since = rates[-1].get("timestamp", 0) + 1
            time.sleep(0.3)
        return all_rates
    except Exception:
        return []


def build_bundles(candles: list[list], funding: list[dict], symbol: str):
    """Build MarketDataBundles from raw data."""
    from app.models.market_data_bundle import MarketDataBundle
    from app.models.market_snapshot import MarketSnapshot

    bundles = []
    history_size = 50

    funding_map = {}
    for fr in funding:
        ts_ms = fr.get("timestamp", 0)
        rate = float(fr.get("fundingRate", 0))
        hour_key = int(ts_ms / 1000) // 3600
        funding_map[hour_key] = rate
    sorted_rates = sorted(funding_map.items())

    for i in range(history_size, len(candles)):
        c = candles[i]
        ts = int(c[0] / 1000)
        price = float(c[4])
        volume = float(c[5])
        spread = price * 0.0002

        snapshot = MarketSnapshot(
            symbol=symbol, price=price, volume=volume,
            bid=price - spread / 2, ask=price + spread / 2,
            timestamp=max(ts, 1),
        )

        start = max(0, i - history_size)
        price_history = [float(candles[j][4]) for j in range(start, i + 1)]
        volume_history = [float(candles[j][5]) for j in range(start, i + 1)]
        oi_history = [float(candles[j][5]) * 0.1 for j in range(start, i + 1)]

        candle_hour = ts // 3600
        funding_history = [r for h, r in sorted_rates if h <= candle_hour]
        if not funding_history:
            funding_history = [0.0]

        bundles.append(MarketDataBundle(
            market=snapshot,
            price_history=price_history,
            volume_history=volume_history,
            oi_history=oi_history,
            funding_history=funding_history,
        ))

    return bundles


def run_backtest_for_symbol(symbol: str, bundles, leverage: float):
    """Run H2 Quantum-Fractal backtest on a single symbol."""
    from app.analytics.feature_engine import FeatureEngine
    from app.backtest.engine import BacktestEngine, TPLevel
    from app.config import Settings
    from app.risk.risk_manager import RiskManager
    from app.strategy.oi_divergence import OIDivergenceStrategy

    settings = Settings(account_equity=10_000.0, paper_trading=True, max_position_pct=MARGIN_PCT)

    # H2: Quantum-Fractal (original winning config)
    h2_levels = [
        TPLevel(pnl_pct=0.1618, close_pct=0.0618, move_sl_to_entry=True),   # TP1: +16.18% margin, close 6.18%
        TPLevel(pnl_pct=1.00,   close_pct=0.1618, move_sl_to_entry=False),  # TP2: +100% margin, close 16.18%
        TPLevel(pnl_pct=2.618,  close_pct=0.50,   move_sl_to_entry=False),  # TP3: +261.8% margin, close 50%
    ]

    engine = BacktestEngine(
        analytics=FeatureEngine(),
        strategy=OIDivergenceStrategy(symbol=symbol),
        risk=RiskManager(settings),
        initial_equity=10_000.0,
        leverage=leverage,
        max_position_pct=MARGIN_PCT,
        tp_levels=h2_levels,
        trailing_stop_atr=1.618,  # Original trailing
    )
    return engine.run(bundles)


def main():
    import ccxt
    exchange = ccxt.okx({"enableRateLimit": True})

    print(f"═══ H2 Quantum-Fractal: Multi-Asset Test ═══")
    print(f"Leverage: {LEVERAGE}x | Timeframe: {TIMEFRAME} | Candles: {CANDLE_LIMIT}")
    print(f"Symbols: {len(SYMBOLS)}")
    print(f"TP: +16.18% (6.18%) → +100% (16.18%) → +261.8% (50%) + trailing 1.618×ATR")
    print()

    results = {}

    for symbol in SYMBOLS:
        short_name = symbol.split("/")[0]
        print(f"[{short_name}] Downloading {CANDLE_LIMIT} candles...", end=" ", flush=True)

        candles = download_candles(exchange, symbol, TIMEFRAME, CANDLE_LIMIT)
        funding = download_funding(exchange, symbol)
        print(f"{len(candles)} candles, {len(funding)} funding rates")

        if len(candles) < 100:
            print(f"  SKIP: not enough data")
            continue

        bundles = build_bundles(candles, funding, symbol)
        if not bundles:
            print(f"  SKIP: no bundles built")
            continue

        result = run_backtest_for_symbol(symbol, bundles, LEVERAGE)
        results[short_name] = result

    # Print comparison table
    print()
    print("=" * 90)
    print(f"{'Asset':<8} {'Trades':>6} {'WR':>6} {'PF':>7} {'Return':>8} {'MDD':>7} {'Sharpe':>7} {'Expect':>8} {'Equity':>10}")
    print("-" * 90)

    total_return = 0
    for name, r in sorted(results.items(), key=lambda x: x[1].total_return_pct, reverse=True):
        pf = f"{r.profit_factor:.2f}" if r.profit_factor < 100 else "inf"
        print(f"{name:<8} {r.total_trades:>6} {r.win_rate:>5.1%} {pf:>7} {r.total_return_pct:>+7.2f}% {r.max_drawdown_pct:>6.2f}% {r.sharpe_ratio:>7.2f} {r.expectancy:>+8.2f} ${r.final_equity:>9.2f}")
        total_return += r.total_return_pct

    print("-" * 90)
    avg_return = total_return / len(results) if results else 0
    print(f"{'AVG':<8} {'':>6} {'':>6} {'':>7} {avg_return:>+7.2f}%")
    print("=" * 90)

    # Best/worst
    if results:
        best = max(results.items(), key=lambda x: x[1].total_return_pct)
        worst = min(results.items(), key=lambda x: x[1].total_return_pct)
        profitable = sum(1 for r in results.values() if r.total_return_pct > 0)
        print(f"\nBest:  {best[0]} ({best[1].total_return_pct:+.2f}%)")
        print(f"Worst: {worst[0]} ({worst[1].total_return_pct:+.2f}%)")
        print(f"Profitable: {profitable}/{len(results)} assets")


if __name__ == "__main__":
    main()
