"""Compare two TP hypotheses on OKX data.

Usage:
    python scripts/test_hypotheses.py

Uses cached data from data/okx_btc_30m.csv and data/okx_funding.json.
If not found, downloads fresh data from OKX.
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_or_download():
    """Load cached data or download from OKX."""
    csv_path = "data/okx_btc_30m.csv"
    funding_path = "data/okx_funding.json"

    if os.path.exists(csv_path) and os.path.exists(funding_path):
        print("Using cached data...")
        from scripts.okx_backtest import build_bundles
        import csv

        candles = []
        with open(csv_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                candles.append([
                    int(row["timestamp"]) * 1000,
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                    float(row["volume"]),
                ])

        with open(funding_path) as f:
            funding = json.load(f)

        bundles = build_bundles(candles, funding)
        return bundles

    print("No cached data found. Downloading from OKX...")
    import ccxt
    from scripts.okx_backtest import download_candles, download_funding_history, build_bundles, save_csv

    exchange = ccxt.okx({"enableRateLimit": True})
    symbol = "BTC/USDT:USDT"
    candles = download_candles(exchange, symbol, "30m", limit=1000)
    funding = download_funding_history(exchange, symbol)
    save_csv(candles, csv_path)
    os.makedirs("data", exist_ok=True)
    with open(funding_path, "w") as f:
        json.dump(funding, f, indent=2, default=str)
    return build_bundles(candles, funding)


def run_test(bundles):
    from app.analytics.feature_engine import FeatureEngine
    from app.backtest.engine import BacktestEngine, TPLevel
    from app.config import Settings
    from app.risk.risk_manager import RiskManager
    from app.strategy.oi_divergence import OIDivergenceStrategy

    settings = Settings(account_equity=10_000.0, paper_trading=True)
    analytics = FeatureEngine()
    risk = RiskManager(settings)
    symbol = "BTC/USDT:USDT"

    PHI = 1.618

    # ═══════════════════════════════════════════════════════════
    # HYPOTHESIS 1: Fibonacci-Kelly (conservative)
    # 4 fixed TP levels based on Fibonacci ratios
    # Close sizes: 8%, 38.2%, 38.2%, 15.6% (Fibonacci-derived)
    # ═══════════════════════════════════════════════════════════
    h1_levels = [
        TPLevel(pnl_pct=0.236,  close_pct=0.08,   move_sl_to_entry=True),   # TP1: +23.6% margin, close 8%
        TPLevel(pnl_pct=0.618,  close_pct=0.382,  move_sl_to_entry=False),  # TP2: +61.8% margin, close 38.2%
        TPLevel(pnl_pct=1.618,  close_pct=0.382,  move_sl_to_entry=False),  # TP3: +161.8% margin, close 38.2%
        TPLevel(pnl_pct=2.618,  close_pct=1.0,    move_sl_to_entry=False),  # TP4: +261.8% margin, close rest
    ]

    # ═══════════════════════════════════════════════════════════
    # HYPOTHESIS 2: Quantum-Fractal (aggressive)
    # 3 TP levels + trailing stop for fat-tail capture
    # Trailing stop = 1.618 × ATR (golden ratio)
    # ═══════════════════════════════════════════════════════════
    h2_levels = [
        TPLevel(pnl_pct=0.1618, close_pct=0.0618, move_sl_to_entry=True),   # TP1: +16.18% margin, close 6.18%
        TPLevel(pnl_pct=1.00,   close_pct=0.1618, move_sl_to_entry=False),  # TP2: +100% margin, close 16.18%
        TPLevel(pnl_pct=2.618,  close_pct=0.50,   move_sl_to_entry=False),  # TP3: +261.8% margin, close 50%
        # Remaining 27.64% rides with trailing stop
    ]

    # ═══════════════════════════════════════════════════════════
    # BASELINE: Original 3-tier (your current settings)
    # ═══════════════════════════════════════════════════════════
    baseline_levels = [
        TPLevel(pnl_pct=0.15, close_pct=0.10, move_sl_to_entry=True),   # TP1: +15%, close 10%
        TPLevel(pnl_pct=1.10, close_pct=0.80, move_sl_to_entry=False),  # TP2: +110%, close 80%
        TPLevel(pnl_pct=2.00, close_pct=1.0,  move_sl_to_entry=False),  # TP3: +200%, close rest
    ]

    configs = {
        "BASELINE (current)": {
            "tp_levels": baseline_levels,
            "trailing_stop_atr": 0.0,
        },
        "H1: Fibonacci-Kelly": {
            "tp_levels": h1_levels,
            "trailing_stop_atr": 0.0,
        },
        "H2: Quantum-Fractal": {
            "tp_levels": h2_levels,
            "trailing_stop_atr": 1.618,
        },
    }

    print(f"\nComparing hypotheses on {len(bundles)} data points (OI Divergence only)")
    print(f"Leverage: 40x | Timeframe: 30min\n")

    # Print TP structure for each hypothesis
    for name, cfg in configs.items():
        print(f"  {name}:")
        for i, tp in enumerate(cfg["tp_levels"]):
            price_move = tp.pnl_pct / 40 * 100
            sl_note = " -> SL to entry" if tp.move_sl_to_entry else ""
            close_note = "close ALL" if tp.close_pct >= 0.999 else f"close {tp.close_pct:.1%}"
            print(f"    TP{i+1}: +{tp.pnl_pct:.1%} margin (price +{price_move:.3f}%) | {close_note}{sl_note}")
        if cfg["trailing_stop_atr"] > 0:
            print(f"    TRAILING: {cfg['trailing_stop_atr']:.3f} × ATR on remaining")
        print()

    print("=" * 70)

    for name, cfg in configs.items():
        strategy = OIDivergenceStrategy(symbol=symbol)
        engine = BacktestEngine(
            analytics=analytics,
            strategy=strategy,
            risk=risk,
            initial_equity=10_000.0,
            leverage=40.0,
            tp_levels=cfg["tp_levels"],
            trailing_stop_atr=cfg["trailing_stop_atr"],
        )
        result = engine.run(bundles)
        print(f"\n{'═' * 30} {name} {'═' * 30}")
        print(result.summary())
        print()

    print("=" * 70)
    print("\nInterpretation:")
    print("  - Higher Profit Factor = more profit per unit of loss")
    print("  - Higher Sharpe = better risk-adjusted return")
    print("  - Lower Max Drawdown = less pain")
    print("  - H1 should be better in ranging market (OI Divergence)")
    print("  - H2 should capture fat-tail moves better")


def main():
    bundles = load_or_download()
    if not bundles:
        print("ERROR: No data available")
        return
    run_test(bundles)


if __name__ == "__main__":
    main()
