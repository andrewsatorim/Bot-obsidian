"""Run ALL strategies over real exchange data (via ccxt) under several configs.

This is the Stage 3 backtest runner. It is data-source agnostic:

- ``--source ccxt`` (default): download real OHLCV / funding / OI from the exchange
  and build :class:`MarketDataBundle` history. This is what we use on the final stage.
- ``--source simulated`` (a.k.a. ``--smoke``): build bundles from the in-process
  :class:`SimulatedDataFeed`. No network. Used to smoke-test that the whole
  pipeline (config -> strategy -> risk -> backtest engine -> metrics -> output)
  runs end to end.

Configs live in the ``CONFIGS`` dict at the top of this file so new profiles can be
added in one place. Each config is an *execution profile* (leverage, margin, ATR
stop multiplier, TP ladder, trailing stop, timeframe) plus a set of strategies to
run it against — either an explicit list of registry names, or ``"ALL"``.

Each (config, strategy) pair is one backtest run. For every run we compute:
total_return_pct, max_drawdown_pct, sharpe_ratio, profit_factor, win_rate,
expectancy, total_trades — and persist them to:

- ``data/backtest_results/{YYYYMMDD_HHMMSS}.json`` — full snapshot of the session
- ``data/backtest_results/history.csv`` — one appended row per run (config params + metrics)

Usage::

    python scripts/run_all_backtests.py --smoke              # offline smoke-test
    python scripts/run_all_backtests.py                      # real ccxt run (final stage)
    python scripts/run_all_backtests.py --configs phi_trailing battle
    python scripts/run_all_backtests.py --candles 1500 --exchange okx
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.analytics.feature_engine import FeatureEngine
from app.backtest.engine import BacktestEngine, BacktestResult, TPLevel
from app.config import Settings
from app.models.market_data_bundle import MarketDataBundle
from app.risk.risk_manager import RiskManager
from app.strategy.bollinger_reversion import BollingerMeanReversionStrategy
from app.strategy.breakout import BreakoutStrategy
from app.strategy.breakout_nooi import BreakoutNoOIStrategy
from app.strategy.candle_volume import CandleVolumeStrategy
from app.strategy.donchian import DonchianStrategy
from app.strategy.elliott import ElliottWaveStrategy
from app.strategy.funding_mean_reversion import FundingMeanReversionStrategy
from app.strategy.liquidation_squeeze import LiquidationSqueezeStrategy
from app.strategy.oi_divergence import OIDivergenceStrategy
from app.strategy.reversal import ReversalStrategy
from app.strategy.swing import SwingStrategy
from app.strategy.trend_following import TrendFollowingStrategy

logger = logging.getLogger("run_all_backtests")

RESULTS_DIR = os.path.join("data", "backtest_results")
HISTORY_CSV = os.path.join(RESULTS_DIR, "history.csv")
DEFAULT_SYMBOL = "BTC/USDT:USDT"


# ---------------------------------------------------------------------------
# Strategy registry — name -> factory(symbol) -> StrategyPort
# ---------------------------------------------------------------------------
# Composite strategies (fusion / super) are intentionally omitted here: they wrap
# the same sub-strategies and are exercised separately. AuraV14 is also omitted: it
# is a Pine Script port with an update(o,h,l,c,v) interface, not a StrategyPort that
# the backtest engine can drive via generate_signal(). Trading logic is untouched.
STRATEGY_REGISTRY: dict[str, Callable[[str], object]] = {
    "OIDivergence": lambda s: OIDivergenceStrategy(symbol=s),
    "TrendFollowing": lambda s: TrendFollowingStrategy(symbol=s),
    "Breakout": lambda s: BreakoutStrategy(symbol=s),
    "BreakoutNoOI": lambda s: BreakoutNoOIStrategy(symbol=s),
    "Bollinger": lambda s: BollingerMeanReversionStrategy(symbol=s),
    "FundingMR": lambda s: FundingMeanReversionStrategy(symbol=s),
    "LiquidationSqueeze": lambda s: LiquidationSqueezeStrategy(symbol=s),
    "Donchian": lambda s: DonchianStrategy(symbol=s),
    "Swing": lambda s: SwingStrategy(symbol=s),
    "Reversal": lambda s: ReversalStrategy(symbol=s),
    "Elliott": lambda s: ElliottWaveStrategy(symbol=s),
    "CandleVolume": lambda s: CandleVolumeStrategy(symbol=s),
}


# ---------------------------------------------------------------------------
# Backtest configs (execution profiles). Add new profiles here.
# ---------------------------------------------------------------------------
@dataclass
class BacktestConfig:
    """A reusable execution profile applied to one or more strategies."""
    name: str
    description: str
    leverage: float
    margin_pct: float          # max_position_pct — fraction of equity used as margin
    atr_mult: float            # ATR stop-loss multiplier
    tp_levels: list[TPLevel]   # take-profit ladder
    trailing_atr: float        # trailing stop in ATR units (0 = disabled)
    timeframe: str             # candle timeframe, e.g. "30m"
    strategies: list[str] | str  # registry names, or "ALL"
    fee_pct: float = 0.0        # taker fee per fill (0 = MEXC zero-fee pairs)
    slippage_pct: float = 0.0005  # adverse fill cost per fill (~half-spread)

    def resolved_strategies(self) -> list[str]:
        if self.strategies == "ALL":
            return list(STRATEGY_REGISTRY.keys())
        return list(self.strategies)

    def tp_as_dicts(self) -> list[dict]:
        return [
            {"pnl_pct": tp.pnl_pct, "close_pct": tp.close_pct, "move_sl_to_entry": tp.move_sl_to_entry}
            for tp in self.tp_levels
        ]


# phi (golden ratio) constants used by the φ-trailing profile
PHI = 1.618

CONFIGS: dict[str, BacktestConfig] = {
    # Боевой профиль — high leverage, breakeven after TP1, wide TP ladder.
    # Applied across ALL strategies.
    "battle": BacktestConfig(
        name="battle",
        description="Боевой: lev 40, TP1 +15%->breakeven, TP2 +110%, TP3 +200%, 30m",
        leverage=40.0,
        margin_pct=0.05,
        atr_mult=1.5,
        tp_levels=[
            TPLevel(pnl_pct=0.15, close_pct=0.30, move_sl_to_entry=True),   # TP1 +15% -> breakeven
            TPLevel(pnl_pct=1.10, close_pct=0.30, move_sl_to_entry=False),  # TP2 +110%
            TPLevel(pnl_pct=2.00, close_pct=1.00, move_sl_to_entry=False),  # TP3 +200% (full close)
        ],
        trailing_atr=0.0,
        timeframe="30m",
        strategies="ALL",
    ),
    # φ-трейлинг — OIDivergence only, golden-ratio TP ladder + φ·ATR trailing stop.
    "phi_trailing": BacktestConfig(
        name="phi_trailing",
        description="φ-trailing: OIDivergence, lev 30, margin 7%, TP +16.18%/+100%/+261.8%, trail 1.618xATR, 30m",
        leverage=30.0,
        margin_pct=0.07,
        atr_mult=1.5,
        tp_levels=[
            TPLevel(pnl_pct=0.1618, close_pct=0.0618, move_sl_to_entry=True),  # TP1 +16.18% -> breakeven
            TPLevel(pnl_pct=1.00, close_pct=0.1618, move_sl_to_entry=False),   # TP2 +100%
            TPLevel(pnl_pct=2.618, close_pct=0.50, move_sl_to_entry=False),    # TP3 +261.8%
        ],
        trailing_atr=PHI,  # 1.618 x ATR
        timeframe="30m",
        strategies=["OIDivergence"],
    ),
    # Conservative scalp profile — lower leverage, tight TP ladder. Applied to all.
    "conservative": BacktestConfig(
        name="conservative",
        description="Conservative: lev 10, TP +8%/+25%/+60%, trail 1.0xATR, 30m",
        leverage=10.0,
        margin_pct=0.05,
        atr_mult=2.0,
        tp_levels=[
            TPLevel(pnl_pct=0.08, close_pct=0.40, move_sl_to_entry=True),
            TPLevel(pnl_pct=0.25, close_pct=0.35, move_sl_to_entry=False),
            TPLevel(pnl_pct=0.60, close_pct=1.00, move_sl_to_entry=False),
        ],
        trailing_atr=1.0,
        timeframe="30m",
        strategies="ALL",
    ),
}


# ---------------------------------------------------------------------------
# Data sources
# ---------------------------------------------------------------------------
def build_bundles_simulated(n: int, symbol: str) -> list[MarketDataBundle]:
    """Build a deterministic-ish list of bundles from the simulated feed (offline)."""
    import asyncio
    import random

    from app.feeds.simulated_feed import SimulatedDataFeed

    random.seed(42)  # reproducible smoke-test
    feed = SimulatedDataFeed()

    async def _collect() -> list[MarketDataBundle]:
        out: list[MarketDataBundle] = []
        for _ in range(n):
            out.append(await feed.get_market_data(symbol))
        return out

    return asyncio.run(_collect())


def build_bundles_ccxt(
    n: int, symbol: str, timeframe: str, exchange_id: str
) -> list[MarketDataBundle]:
    """Download real OHLCV (+ funding) via ccxt and build rolling-window bundles.

    Open-interest history is best-effort (not all venues expose it through ccxt);
    when unavailable, oi_history falls back to a flat series so OI-aware strategies
    simply produce no divergence signal rather than crash.
    """
    import time

    import ccxt

    from app.models.market_snapshot import MarketSnapshot

    exchange = getattr(ccxt, exchange_id)({"enableRateLimit": True})

    logger.info("downloading %d %s candles for %s from %s", n, timeframe, symbol, exchange_id)
    candles: list[list] = []
    end_ts = int(time.time() * 1000)
    while len(candles) < n:
        batch = min(300, n - len(candles))
        params = {"before": str(end_ts)} if candles else {}
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=batch, params=params)
        if not ohlcv:
            break
        seen = {c[0] for c in candles}
        fresh = [c for c in ohlcv if c[0] not in seen]
        if not fresh:
            break
        candles.extend(fresh)
        end_ts = min(c[0] for c in fresh)
        time.sleep(exchange.rateLimit / 1000.0)
    candles.sort(key=lambda c: c[0])

    # Funding history (best effort)
    funding_by_hour: dict[int, float] = {}
    try:
        fr = exchange.fetch_funding_rate_history(symbol, limit=500)
        for r in fr:
            ts = int(r.get("timestamp") or 0)
            rate = float(r.get("fundingRate") or 0.0)
            if ts:
                funding_by_hour[ts // (3600 * 1000)] = rate
    except Exception as exc:  # noqa: BLE001 — funding is optional context
        logger.warning("funding history unavailable: %s", exc)

    window = 50
    bundles: list[MarketDataBundle] = []
    for i in range(window, len(candles)):
        c = candles[i]
        ts, close, vol = int(c[0]), float(c[4]), float(c[5])
        spread = close * 0.0001
        snap = MarketSnapshot(
            symbol=symbol, price=close, volume=vol,
            bid=close - spread / 2, ask=close + spread / 2,
            timestamp=max(int(ts / 1000), 1),
        )
        ph = [float(candles[j][4]) for j in range(i - window, i + 1)]
        vh = [float(candles[j][5]) for j in range(i - window, i + 1)]
        fh = [r for h, r in sorted(funding_by_hour.items()) if h <= ts // (3600 * 1000)] or [0.0]
        bundles.append(MarketDataBundle(
            market=snap, price_history=ph, volume_history=vh,
            oi_history=[0.0], funding_history=fh,
            liquidation_above=close * 1.02, liquidation_below=close * 0.98,
        ))
    logger.info("built %d bundles", len(bundles))
    return bundles


# ---------------------------------------------------------------------------
# Run a single (config, strategy) backtest
# ---------------------------------------------------------------------------
@dataclass
class RunRecord:
    config: str
    strategy: str
    symbol: str
    timeframe: str
    params: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)


METRIC_KEYS = (
    "total_return_pct",
    "max_drawdown_pct",
    "sharpe_ratio",
    "profit_factor",
    "win_rate",
    "expectancy",
    "total_trades",
)


def _metrics(result: BacktestResult) -> dict:
    pf = result.profit_factor
    out = {
        "total_return_pct": round(result.total_return_pct, 4),
        "max_drawdown_pct": round(result.max_drawdown_pct, 4),
        "sharpe_ratio": round(result.sharpe_ratio, 4),
        "profit_factor": round(pf, 4) if pf != float("inf") else None,
        "win_rate": round(result.win_rate, 4),
        "expectancy": round(result.expectancy, 4),
        "total_trades": result.total_trades,
    }
    return out


def run_one(
    config: BacktestConfig,
    strategy_name: str,
    bundles: list[MarketDataBundle],
    symbol: str,
    initial_equity: float,
) -> RunRecord:
    strategy = STRATEGY_REGISTRY[strategy_name](symbol)
    settings = Settings(
        account_equity=initial_equity,
        paper_trading=True,
        max_position_pct=config.margin_pct,
    )
    engine = BacktestEngine(
        analytics=FeatureEngine(),
        strategy=strategy,
        risk=RiskManager(settings),
        initial_equity=initial_equity,
        atr_risk_multiplier=config.atr_mult,
        max_position_pct=config.margin_pct,
        leverage=config.leverage,
        tp_levels=config.tp_levels,
        trailing_stop_atr=config.trailing_atr,
        fee_pct=config.fee_pct,
        slippage_pct=config.slippage_pct,
    )
    result = engine.run(bundles)
    return RunRecord(
        config=config.name,
        strategy=strategy_name,
        symbol=symbol,
        timeframe=config.timeframe,
        params={
            "leverage": config.leverage,
            "margin_pct": config.margin_pct,
            "atr_mult": config.atr_mult,
            "trailing_atr": config.trailing_atr,
            "fee_pct": config.fee_pct,
            "slippage_pct": config.slippage_pct,
            "tp_levels": config.tp_as_dicts(),
            "initial_equity": initial_equity,
        },
        metrics=_metrics(result),
    )


# ---------------------------------------------------------------------------
# Risk-adjusted ranking
# ---------------------------------------------------------------------------
@dataclass
class RankedResult:
    """A backtest result annotated with its risk-adjusted rank."""
    result: object             # the original RunRecord (or any metrics carrier)
    sharpe: float
    profit_factor: float       # float('inf') when undefined (no losing trades)
    total_return_pct: float
    max_drawdown_pct: float    # magnitude (always >= 0)
    passed_dd_filter: bool
    rank: int | None           # 1-based among survivors; None if filtered out
    is_winner: bool


def _result_metric(r: object, key: str):
    """Read a metric from a RunRecord, a {'metrics': {...}} dict, or a flat dict."""
    if hasattr(r, "metrics"):
        m = r.metrics
    elif isinstance(r, dict) and "metrics" in r:
        m = r["metrics"]
    elif isinstance(r, dict):
        m = r
    else:
        m = getattr(r, "__dict__", {})
    return m.get(key)


def _num(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def rank_results(results: list, max_dd_threshold: float = -35.0) -> list[RankedResult]:
    """Rank backtest results by a RISK-ADJUSTED score, not by raw return.

    Steps:
    1. Filter out configs whose max drawdown is worse than ``max_dd_threshold``
       (default -35%). The threshold is given as a signed percentage; only its
       magnitude matters, so -35.0 and 35.0 are equivalent — a result is rejected
       when its drawdown magnitude exceeds 35%.
    2. Among survivors, rank by Sharpe ratio (primary), with profit_factor as the
       tie-breaker and total_return_pct only as a final, secondary tie-breaker.

    Returns every result as a :class:`RankedResult`, survivors first (sorted best
    to worst), then the drawdown-rejected ones (also sorted, but ``rank=None``).
    The single best survivor is flagged ``is_winner=True``.
    """
    dd_limit = abs(max_dd_threshold)
    ranked: list[RankedResult] = []
    for r in results:
        pf_raw = _result_metric(r, "profit_factor")
        pf = float("inf") if pf_raw is None else _num(pf_raw)
        dd = abs(_num(_result_metric(r, "max_drawdown_pct")))
        ranked.append(RankedResult(
            result=r,
            sharpe=_num(_result_metric(r, "sharpe_ratio")),
            profit_factor=pf,
            total_return_pct=_num(_result_metric(r, "total_return_pct")),
            max_drawdown_pct=dd,
            passed_dd_filter=dd <= dd_limit,
            rank=None,
            is_winner=False,
        ))

    # Risk-adjusted sort key: Sharpe -> profit_factor -> total_return (all desc).
    sort_key = lambda x: (x.sharpe, x.profit_factor, x.total_return_pct)  # noqa: E731

    survivors = sorted((x for x in ranked if x.passed_dd_filter), key=sort_key, reverse=True)
    rejected = sorted((x for x in ranked if not x.passed_dd_filter), key=sort_key, reverse=True)

    for i, x in enumerate(survivors, start=1):
        x.rank = i
    if survivors:
        survivors[0].is_winner = True

    return survivors + rejected


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def persist(ranked: list[RankedResult], meta: dict) -> str:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    stamp = meta["timestamp"]

    # Full JSON snapshot (already ordered best-to-worst by rank_results)
    json_path = os.path.join(RESULTS_DIR, f"{stamp}.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "meta": meta,
                "runs": [
                    {
                        "rank": x.rank, "is_winner": x.is_winner,
                        "passed_dd_filter": x.passed_dd_filter,
                        "config": x.result.config, "strategy": x.result.strategy,
                        "symbol": x.result.symbol, "timeframe": x.result.timeframe,
                        "params": x.result.params, "metrics": x.result.metrics,
                    }
                    for x in ranked
                ],
            },
            fh,
            indent=2,
        )

    # Append to history.csv (flat: rank + config params + metrics)
    fieldnames = [
        "timestamp", "source", "rank", "is_winner", "passed_dd_filter",
        "config", "strategy", "symbol", "timeframe",
        "leverage", "margin_pct", "atr_mult", "trailing_atr",
        "fee_pct", "slippage_pct", "tp_ladder",
        "initial_equity", *METRIC_KEYS,
    ]
    write_header = not os.path.exists(HISTORY_CSV)
    with open(HISTORY_CSV, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        for x in ranked:
            r = x.result
            ladder = "|".join(
                f"+{tp['pnl_pct']:.4g}:{tp['close_pct']:.4g}{'^' if tp['move_sl_to_entry'] else ''}"
                for tp in r.params["tp_levels"]
            )
            writer.writerow({
                "timestamp": stamp,
                "source": meta["source"],
                "rank": x.rank if x.rank is not None else "",
                "is_winner": x.is_winner,
                "passed_dd_filter": x.passed_dd_filter,
                "config": r.config,
                "strategy": r.strategy,
                "symbol": r.symbol,
                "timeframe": r.timeframe,
                "leverage": r.params["leverage"],
                "margin_pct": r.params["margin_pct"],
                "atr_mult": r.params["atr_mult"],
                "trailing_atr": r.params["trailing_atr"],
                "fee_pct": r.params["fee_pct"],
                "slippage_pct": r.params["slippage_pct"],
                "tp_ladder": ladder,
                "initial_equity": r.params["initial_equity"],
                **r.metrics,
            })
    return json_path


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def print_ranked_table(ranked: list[RankedResult], max_dd_threshold: float) -> None:
    """Print results sorted by risk-adjusted rank, with the winner flagged.

    Sort: Sharpe (primary) -> profit_factor -> total_return, after rejecting any
    config whose max drawdown is worse than ``max_dd_threshold``.
    """
    header = (
        f"{'#':>3} {'Config':<14} {'Strategy':<18} {'Trades':>6} {'WR':>6} {'PF':>7} "
        f"{'Return':>9} {'MDD':>8} {'Sharpe':>7} {'Expect':>9}  Flag"
    )
    print(f"Ranking by risk-adjusted score (Sharpe > PF > return); "
          f"max-DD filter = {max_dd_threshold:.1f}%")
    print("=" * (len(header) + 4))
    print(header)
    print("-" * (len(header) + 4))
    for x in ranked:
        r = x.result
        m = r.metrics
        pf = "inf" if m["profit_factor"] is None else f"{m['profit_factor']:.2f}"
        if not x.passed_dd_filter:
            rank_cell, flag = "  -", f"✗ DD>{abs(max_dd_threshold):.0f}%"
        else:
            rank_cell = f"{x.rank:>3}"
            flag = "★ WINNER" if x.is_winner else ""
        print(
            f"{rank_cell} {r.config:<14} {r.strategy:<18} {m['total_trades']:>6} {m['win_rate']:>5.1%} {pf:>7}"
            f" {m['total_return_pct']:>+8.2f}% {m['max_drawdown_pct']:>7.2f}% {m['sharpe_ratio']:>7.2f}"
            f" {m['expectancy']:>+9.2f}  {flag}"
        )
    print("=" * (len(header) + 4))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run all strategies across backtest configs.")
    p.add_argument("--source", choices=["ccxt", "simulated"], default="ccxt",
                   help="Data source. 'simulated' = offline smoke-test.")
    p.add_argument("--smoke", action="store_true",
                   help="Shortcut for --source simulated with a small candle count.")
    p.add_argument("--configs", nargs="*", default=None,
                   help=f"Subset of configs to run. Available: {', '.join(CONFIGS)}")
    p.add_argument("--symbol", default=DEFAULT_SYMBOL)
    p.add_argument("--exchange", default="okx", help="ccxt exchange id (ccxt source only)")
    p.add_argument("--candles", type=int, default=1500, help="Number of candles to load")
    p.add_argument("--equity", type=float, default=10_000.0, help="Initial equity")
    p.add_argument("--max-dd", type=float, default=-35.0, dest="max_dd",
                   help="Max-drawdown filter for ranking (signed %%, default -35.0)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = parse_args(argv)

    source = "simulated" if args.smoke else args.source
    n_candles = 200 if args.smoke else args.candles

    selected = args.configs or list(CONFIGS)
    unknown = [c for c in selected if c not in CONFIGS]
    if unknown:
        print(f"Unknown config(s): {unknown}. Available: {list(CONFIGS)}", file=sys.stderr)
        return 2
    configs = [CONFIGS[c] for c in selected]

    # All selected configs share a timeframe for the data pull; use the first.
    # (Every required config is 30m; mixed timeframes would need per-config pulls.)
    timeframe = configs[0].timeframe

    if source == "simulated":
        bundles = build_bundles_simulated(n_candles, args.symbol)
    else:
        bundles = build_bundles_ccxt(n_candles, args.symbol, timeframe, args.exchange)

    if not bundles:
        print("ERROR: no data bundles were built.", file=sys.stderr)
        return 1

    records: list[RunRecord] = []
    for config in configs:
        for strategy_name in config.resolved_strategies():
            rec = run_one(config, strategy_name, bundles, args.symbol, args.equity)
            records.append(rec)

    ranked = rank_results(records, max_dd_threshold=args.max_dd)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    meta = {
        "timestamp": timestamp,
        "source": source,
        "symbol": args.symbol,
        "exchange": args.exchange if source == "ccxt" else None,
        "timeframe": timeframe,
        "candles": len(bundles),
        "initial_equity": args.equity,
        "configs": selected,
        "max_dd_threshold": args.max_dd,
    }

    print_ranked_table(ranked, args.max_dd)
    json_path = persist(ranked, meta)
    print(f"\nSaved {len(records)} runs:")
    print(f"  JSON:    {json_path}")
    print(f"  history: {HISTORY_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
