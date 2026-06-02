"""Fast-vector strategy selection: rank the signal-engine strategies on short TFs.

Drives the EXISTING backtest harness (scripts/run_all_backtests.py) across a
basket of liquid, volatile alts that pass the x2 filter — at the fast vector's
own horizon (15m / optionally 5m) — and aggregates a risk-ranked table
(Sharpe + drawdown) plus a 3-window walk-forward robustness count per strategy.

It reuses run_all_backtests' data loader, run_one, rank_results and the backtest
engine's walk-forward — no strategy or ranking logic is reimplemented here. It
writes nothing to any SIGNAL_ config; it only reports a ranking for a human to
choose SIGNAL_STRATEGY_NAME.

Data source is binanceusdm (USDM perps): OKX's public candles endpoint only
serves ~recent history (~15 days), too shallow for a multi-month window, so the
ranking is computed on Binance perp data for the same alts. The live signal
engine still runs on OKX — acceptable for a strategy-ranking proxy.

Usage:
    python scripts/fast_vector_backtest.py [config] [lookback_days]
    config        : fast15 (default) | fast5
    lookback_days : days of history per symbol (default 70 ~= 2.3 months)
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone

from app.analytics.feature_engine import FeatureEngine
from app.backtest.engine import BacktestEngine
from app.config import Settings
from app.risk.risk_manager import RiskManager
from scripts.run_all_backtests import (
    CONFIGS,
    RESULTS_DIR,
    STRATEGY_REGISTRY,
    build_bundles_ccxt,
    rank_results,
    run_one,
)

BASKET = [
    "SOL/USDT:USDT", "NEAR/USDT:USDT", "SUI/USDT:USDT", "WLD/USDT:USDT",
    "ARB/USDT:USDT", "APT/USDT:USDT", "INJ/USDT:USDT", "TIA/USDT:USDT",
]
EXCHANGE = "binanceusdm"  # deep history; OKX public candles only serve ~15d
EQUITY = 10_000.0
MAX_DD = -35.0
WF_WINDOWS = 3


def _walk_forward(config, strategy_name: str, bundles, symbol: str):
    """Run the engine's 3-window walk-forward exactly as run_all_backtests does."""
    settings = Settings(account_equity=EQUITY, paper_trading=True, max_position_pct=config.margin_pct)
    engine = BacktestEngine(
        analytics=FeatureEngine(),
        strategy=STRATEGY_REGISTRY[strategy_name](symbol),
        risk=RiskManager(settings),
        initial_equity=EQUITY,
        atr_risk_multiplier=config.atr_mult,
        max_position_pct=config.margin_pct,
        leverage=config.leverage,
        tp_levels=config.tp_levels,
        trailing_stop_atr=config.trailing_atr,
        fee_pct=config.fee_pct,
        slippage_pct=config.slippage_pct,
    )
    return engine.run_walk_forward(
        bundles, n_windows=WF_WINDOWS, min_profitable_windows=2,
        strategy_factory=lambda n=strategy_name: STRATEGY_REGISTRY[n](symbol),
    )


def main() -> None:
    config_name = sys.argv[1] if len(sys.argv) > 1 else "fast15"
    lookback_days = int(sys.argv[2]) if len(sys.argv) > 2 else 70
    config = CONFIGS[config_name]
    strategies = config.resolved_strategies()

    print(f"=== Fast-vector backtest: {config_name} ({config.timeframe}), "
          f"~{lookback_days}d, {len(BASKET)} symbols, {EXCHANGE}, fees+slippage ===\n")

    # per_symbol[symbol][strategy] = {"metrics": {...}, "wf": {...}} ; failures recorded.
    per_symbol: dict[str, dict] = {}
    failures: list[str] = []

    for symbol in BASKET:
        try:
            t0 = time.time()
            bundles = build_bundles_ccxt(0, symbol, config.timeframe, EXCHANGE,
                                         lookback_days=lookback_days)
            print(f"[{symbol}] {len(bundles)} bundles in {time.time() - t0:.1f}s")
        except Exception as exc:  # noqa: BLE001
            print(f"[{symbol}] DATA FETCH FAILED: {type(exc).__name__}: {str(exc)[:120]}")
            failures.append(f"{symbol}: {type(exc).__name__}")
            continue

        recs = {}
        records = []
        for strat in strategies:
            rec = run_one(config, strat, bundles, symbol, EQUITY)  # one backtest per strategy
            records.append(rec)
            wf = _walk_forward(config, strat, bundles, symbol)
            recs[strat] = {
                "metrics": rec.metrics,
                "wf": {"window_returns_pct": [round(r, 3) for r in wf.window_returns_pct],
                       "profitable_windows": wf.profitable_windows,
                       "robust": wf.robust},
            }
        per_symbol[symbol] = recs

        # Per-symbol risk-ranked line (best strategy for this alt) — reuse the records.
        ranked = rank_results(records, MAX_DD)
        winner = next((x for x in ranked if x.is_winner), None)
        if winner:
            print(f"    best: {winner.result.strategy:<14} "
                  f"Sharpe {winner.sharpe:+.2f}  DD {winner.max_drawdown_pct:.1f}%  "
                  f"ret {winner.total_return_pct:+.1f}%")

    if not per_symbol:
        print("\nNo symbols produced data — aborting (likely rate-limit / network). "
              f"Failures: {failures}")
        return

    # -------- Aggregate per strategy across the basket --------
    agg = []
    for strat in strategies:
        rows = [per_symbol[s][strat] for s in per_symbol if strat in per_symbol[s]]
        if not rows:
            continue
        sharpes = [r["metrics"].get("sharpe_ratio", 0.0) for r in rows]
        dds = [abs(r["metrics"].get("max_drawdown_pct", 0.0)) for r in rows]
        rets = [r["metrics"].get("total_return_pct", 0.0) for r in rows]
        trades = [r["metrics"].get("total_trades", 0) for r in rows]
        robust = sum(1 for r in rows if r["wf"]["robust"])
        agg.append({
            "strategy": strat,
            "symbols": len(rows),
            "mean_sharpe": sum(sharpes) / len(sharpes),
            "mean_return_pct": sum(rets) / len(rets),
            "mean_dd_pct": sum(dds) / len(dds),
            "worst_dd_pct": max(dds) if dds else 0.0,
            "mean_trades": sum(trades) / len(trades),
            "robust_symbols": robust,
            "robust_total": len(rows),
        })

    # Rank by mean Sharpe, drawdown as tie-breaker (lower is better).
    agg.sort(key=lambda a: (a["mean_sharpe"], -a["mean_dd_pct"]), reverse=True)

    print(f"\n=== AGGREGATE risk ranking across {len(per_symbol)} alts ({config.timeframe}) ===")
    hdr = f"{'#':>2} {'Strategy':<14} {'meanSharpe':>10} {'meanDD%':>8} {'worstDD%':>9} {'meanRet%':>9} {'meanTr':>7} {'WF robust':>10}"
    print(hdr)
    print("-" * len(hdr))
    for i, a in enumerate(agg, 1):
        print(f"{i:>2} {a['strategy']:<14} {a['mean_sharpe']:>+10.2f} {a['mean_dd_pct']:>8.1f} "
              f"{a['worst_dd_pct']:>9.1f} {a['mean_return_pct']:>+9.1f} {a['mean_trades']:>7.0f} "
              f"{a['robust_symbols']:>4}/{a['robust_total']:<5}")
    if failures:
        print(f"\nSymbols skipped (data/fetch issues): {failures}")

    # -------- Persist --------
    os.makedirs(RESULTS_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = os.path.join(RESULTS_DIR, f"fast_vector_{config_name}_{stamp}.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump({
            "meta": {"config": config_name, "timeframe": config.timeframe,
                     "lookback_days": lookback_days, "basket": BASKET, "exchange": EXCHANGE,
                     "max_dd_threshold": MAX_DD, "wf_windows": WF_WINDOWS,
                     "failures": failures, "timestamp": stamp},
            "aggregate": agg,
            "per_symbol": per_symbol,
        }, fh, indent=2)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
