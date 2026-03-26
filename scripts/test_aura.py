"""Backtest Aura V14 strategy on OKX 30min BTC data.

Config:
  TF: 30min
  Leverage: 40x
  Margin: 15%
  TP1: +15% on margin (price +0.375%) -> close 10%
  TP2: +50% on margin (price +1.25%) -> close 60%
  TP3: +300% on margin (price +7.5%) -> close rest
  On reverse signal: FLIP position
  SL: UT Bot trailing stop (ATR(1) * 5.0)

Usage:
    python scripts/test_aura.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.strategy.aura_v14 import AuraV14

SYMBOL = "BTC-USDT-SWAP"
BASE_URL = "https://www.okx.com"
COINGLASS_KEY = "7abff9b1c52e41ddaff0d72ff2a8da09"
LEVERAGE = 40
MARGIN_PCT = 0.15
FEE_RATE = 0.001

TP_LEVELS = [
    (0.15, 0.10),   # TP1: +15% margin -> close 10%
    (0.50, 0.60),   # TP2: +50% margin -> close 60%
    (3.00, 1.00),   # TP3: +300% margin -> close rest
]


def okx_get(path, params=None):
    resp = requests.get(f"{BASE_URL}{path}", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def download_candles(inst_id, bar="30m", limit=1500):
    print(f"Downloading {limit} candles ({bar})...", end=" ", flush=True)
    all_c = []
    after = ""
    while len(all_c) < limit:
        params = {"instId": inst_id, "bar": bar, "limit": "300"}
        if after:
            params["after"] = after
        data = okx_get("/api/v5/market/candles", params)
        candles = data.get("data", [])
        if not candles:
            break
        for c in candles:
            # [ts, open, high, low, close, vol_contracts, volCcy, volCcyQuote, confirm]
            all_c.append([
                int(c[0]),      # ts
                float(c[1]),    # open
                float(c[2]),    # high
                float(c[3]),    # low
                float(c[4]),    # close
                float(c[5]),    # vol (contracts)
                float(c[7]),    # volCcyQuote (USDT volume)
            ])
        after = candles[-1][0]
        print(f"{len(all_c)}", end="..", flush=True)
        time.sleep(0.2)
    all_c.sort(key=lambda c: c[0])
    seen = set()
    unique = [c for c in all_c if c[0] not in seen and not seen.add(c[0])]
    print(f" total={len(unique)}")
    return unique


def coinglass_get(path, params=None):
    headers = {"accept": "application/json", "CG-API-KEY": COINGLASS_KEY}
    resp = requests.get(f"https://open-api-v3.coinglass.com{path}", headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_coinglass_oi():
    """Fetch aggregated OI from Coinglass for additional filter."""
    print("Fetching Coinglass OI + liquidation...", end=" ", flush=True)
    result = {"oi_data": [], "ls_ratio": []}
    try:
        data = coinglass_get("/api/futures/openInterest/ohlc-history",
                            {"symbol": "BTC", "interval": "30m", "limit": "500"})
        oi = data.get("data", [])
        if isinstance(oi, list):
            result["oi_data"] = oi
            print(f"oi({len(oi)})", end="..", flush=True)
    except Exception as e:
        print(f"oi_err:{e}", end="..", flush=True)

    try:
        data = coinglass_get("/api/futures/globalLongShortAccountRatio/chart",
                            {"symbol": "BTC", "interval": "30m", "limit": "500"})
        ls = data.get("data", [])
        if isinstance(ls, list):
            result["ls_ratio"] = ls
            print(f"ls({len(ls)})", end="..", flush=True)
    except Exception as e:
        print(f"ls_err:{e}", end="..", flush=True)

    try:
        data = coinglass_get("/api/futures/liquidation/v2/info", {"symbol": "BTC"})
        result["liq_info"] = data.get("data", {})
        print("liq", end="..", flush=True)
    except Exception as e:
        print(f"liq_err:{e}", end="..", flush=True)

    print(" done")
    return result


def build_oi_filter(cg_data, candles):
    """Build OI and long/short ratio lookup for signal filtering.

    Returns dict: candle_index -> {oi_change_pct, ls_ratio}
    """
    oi_map = {}
    for r in cg_data.get("oi_data", []):
        if isinstance(r, dict):
            ts = int(r.get("t", r.get("ts", 0)))
            val = float(r.get("o", r.get("oi", 0)))
            if ts > 0 and val > 0:
                bucket = ts // (30*60*1000) * (30*60*1000)
                oi_map[bucket] = val

    ls_map = {}
    for r in cg_data.get("ls_ratio", []):
        if isinstance(r, dict):
            ts = int(r.get("t", r.get("ts", 0)))
            ratio = float(r.get("longRate", r.get("value", 0.5)))
            if ts > 0:
                bucket = ts // (30*60*1000) * (30*60*1000)
                ls_map[bucket] = ratio

    # Build per-candle filter data
    filters = {}
    prev_oi = 0
    for idx, c in enumerate(candles):
        ts = c[0]
        bucket = ts // (30*60*1000) * (30*60*1000)
        oi = oi_map.get(bucket, 0)
        ls = ls_map.get(bucket, 0.5)

        oi_change = 0.0
        if prev_oi > 0 and oi > 0:
            oi_change = (oi - prev_oi) / prev_oi
        if oi > 0:
            prev_oi = oi

        filters[idx] = {
            "oi": oi,
            "oi_change": oi_change,
            "ls_ratio": ls,
            "has_data": oi > 0,
        }

    coverage = sum(1 for f in filters.values() if f["has_data"])
    print(f"OI filter coverage: {coverage}/{len(candles)} ({coverage/max(len(candles),1)*100:.0f}%)")
    return filters


@dataclass
class Position:
    direction: str  # "LONG" or "SHORT"
    entry_price: float
    quantity: float
    initial_quantity: float
    margin: float
    tp_hit: list[bool] = field(default_factory=lambda: [False, False, False])
    realized_pnl: float = 0.0


@dataclass
class Trade:
    direction: str
    entry_price: float
    exit_price: float
    pnl: float
    tp_hits: int
    exit_reason: str
    entry_idx: int
    exit_idx: int


def run_backtest(candles, oi_filters=None):
    aura = AuraV14()
    equity = 10_000.0
    equity_curve = [equity]
    trades: list[Trade] = []
    position: Position | None = None
    signals_count = 0

    for idx, c in enumerate(candles):
        ts, o, h, l, close, vol_contracts, vol_usdt = c

        # Feed candle to Aura
        signal = aura.update(o, h, l, close, vol_usdt)

        # --- CHECK TP LEVELS on open position ---
        if position is not None:
            # Use high/low for intra-candle TP detection
            if position.direction == "LONG":
                pnl_best = (h - position.entry_price) * position.quantity  # Best PnL this candle
                pnl_close = (close - position.entry_price) * position.quantity
                pnl_worst = (l - position.entry_price) * position.quantity
            else:
                pnl_best = (position.entry_price - l) * position.quantity
                pnl_close = (position.entry_price - close) * position.quantity
                pnl_worst = (position.entry_price - h) * position.quantity

            margin = position.entry_price * position.initial_quantity / LEVERAGE
            pnl_pct_best = pnl_best / margin if margin > 0 else 0
            pnl_pct_close = pnl_close / margin if margin > 0 else 0
            pnl_pct_worst = pnl_worst / margin if margin > 0 else 0

            # --- STOP LOSS: -50% on margin ---
            if pnl_pct_worst <= -0.50:
                total_pnl = pnl_worst + position.realized_pnl
                fee = close * position.quantity * FEE_RATE
                equity += total_pnl - fee
                trades.append(Trade(position.direction, position.entry_price, close, total_pnl - fee, sum(position.tp_hit), "SL(-50%)", 0, idx))
                position = None
                equity_curve.append(equity)
                continue

            # Check TPs using BEST pnl this candle (high for LONG, low for SHORT)
            for i in range(len(TP_LEVELS) - 1, -1, -1):
                tp_pct, close_pct = TP_LEVELS[i]
                if position.tp_hit[i]:
                    continue

                if pnl_pct_best >= tp_pct:
                    position.tp_hit[i] = True
                    if close_pct >= 0.99:
                        # Full close
                        total_pnl = pnl + position.realized_pnl
                        fee = close * position.quantity * FEE_RATE
                        equity += total_pnl - fee
                        trades.append(Trade(position.direction, position.entry_price, close, total_pnl - fee, sum(position.tp_hit), f"TP{i+1}", 0, idx))
                        position = None
                    else:
                        close_qty = position.initial_quantity * close_pct
                        close_qty = min(close_qty, position.quantity)
                        if position.direction == "LONG":
                            partial = (close - position.entry_price) * close_qty
                        else:
                            partial = (position.entry_price - close) * close_qty
                        fee = close * close_qty * FEE_RATE
                        position.quantity -= close_qty
                        position.realized_pnl += partial - fee
                        if position.quantity <= 0.0001:
                            equity += position.realized_pnl
                            trades.append(Trade(position.direction, position.entry_price, close, position.realized_pnl, sum(position.tp_hit), f"TP{i+1}", 0, idx))
                            position = None
                    break

        # --- SIGNAL: FLIP or OPEN ---
        if signal is not None:
            signals_count += 1
            new_dir = "LONG" if signal == "BUY" else "SHORT"

            # Coinglass OI filter: skip if OI data says weak signal
            skip_signal = False
            if oi_filters and idx in oi_filters:
                f = oi_filters[idx]
                if f["has_data"]:
                    # Filter: don't LONG if long/short ratio > 0.65 (too many longs = crowded)
                    if new_dir == "LONG" and f["ls_ratio"] > 0.65:
                        skip_signal = True
                    # Filter: don't SHORT if long/short ratio < 0.35 (too many shorts)
                    if new_dir == "SHORT" and f["ls_ratio"] < 0.35:
                        skip_signal = True
                    # Filter: don't enter if OI dropping > 3% (unstable market)
                    if f["oi_change"] < -0.03:
                        skip_signal = True

            if skip_signal:
                equity_curve.append(equity)
                continue

            # Close existing position if opposite direction
            if position is not None and position.direction != new_dir:
                if position.direction == "LONG":
                    pnl = (close - position.entry_price) * position.quantity
                else:
                    pnl = (position.entry_price - close) * position.quantity
                fee = close * position.quantity * FEE_RATE
                total = pnl + position.realized_pnl - fee
                equity += total
                trades.append(Trade(position.direction, position.entry_price, close, total, sum(position.tp_hit), "FLIP", 0, idx))
                position = None

            # Open new position
            if position is None:
                margin = equity * MARGIN_PCT
                notional = margin * LEVERAGE
                qty = notional / close if close > 0 else 0
                entry_fee = notional * FEE_RATE
                equity -= entry_fee

                position = Position(
                    direction=new_dir,
                    entry_price=close,
                    quantity=qty,
                    initial_quantity=qty,
                    margin=margin,
                )

        equity_curve.append(equity)

    # Force close at end
    if position is not None:
        if position.direction == "LONG":
            pnl = (candles[-1][4] - position.entry_price) * position.quantity
        else:
            pnl = (position.entry_price - candles[-1][4]) * position.quantity
        fee = candles[-1][4] * position.quantity * FEE_RATE
        total = pnl + position.realized_pnl - fee
        equity += total
        trades.append(Trade(position.direction, position.entry_price, candles[-1][4], total, sum(position.tp_hit), "END", 0, len(candles)-1))
        equity_curve[-1] = equity

    return trades, equity_curve, signals_count


def print_results(trades, equity_curve, signals_count, n_candles):
    equity_start = 10_000.0
    equity_end = equity_curve[-1]
    total_return = (equity_end - equity_start) / equity_start * 100

    winners = [t for t in trades if t.pnl > 0]
    losers = [t for t in trades if t.pnl <= 0]
    win_rate = len(winners) / len(trades) * 100 if trades else 0

    gross_profit = sum(t.pnl for t in winners)
    gross_loss = abs(sum(t.pnl for t in losers))
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    # Max drawdown
    peak = equity_curve[0]
    max_dd = 0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100
        if dd > max_dd:
            max_dd = dd

    # Sharpe
    if len(equity_curve) > 1:
        import statistics
        returns = [(equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1]
                   for i in range(1, len(equity_curve)) if equity_curve[i-1] > 0]
        if returns:
            m = statistics.mean(returns)
            s = statistics.pstdev(returns)
            sharpe = (m / s) * (365 * 48) ** 0.5 if s > 0 else 0  # 48 candles/day for 30min
        else:
            sharpe = 0
    else:
        sharpe = 0

    days = n_candles * 30 / 60 / 24

    # Exit reasons
    reasons = {}
    for t in trades:
        reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1

    print(f"\n{'='*60}")
    print(f"  AURA V14 BACKTEST RESULTS")
    print(f"{'='*60}")
    print(f"  Data:           {n_candles} candles (30min) = {days:.0f} days")
    print(f"  Leverage:       {LEVERAGE}x")
    print(f"  Margin:         {MARGIN_PCT*100:.0f}%")
    print(f"  Signals:        {signals_count}")
    print(f"  Total trades:   {len(trades)}")
    print(f"  Win rate:       {win_rate:.1f}%")
    print(f"  Profit factor:  {pf:.2f}")
    print(f"  Total return:   {total_return:+.2f}%")
    print(f"  Max drawdown:   {max_dd:.2f}%")
    print(f"  Sharpe ratio:   {sharpe:.2f}")
    print(f"  Final equity:   ${equity_end:,.2f}")
    print(f"")
    print(f"  Exit reasons:")
    for reason, count in sorted(reasons.items()):
        print(f"    {reason}: {count}")
    print(f"")
    if trades:
        avg_pnl = sum(t.pnl for t in trades) / len(trades)
        best = max(trades, key=lambda t: t.pnl)
        worst = min(trades, key=lambda t: t.pnl)
        print(f"  Avg trade PnL:  ${avg_pnl:+.2f}")
        print(f"  Best trade:     ${best.pnl:+.2f} ({best.direction} -> {best.exit_reason})")
        print(f"  Worst trade:    ${worst.pnl:+.2f} ({worst.direction} -> {worst.exit_reason})")

        # Flip stats
        flips = [t for t in trades if t.exit_reason == "FLIP"]
        if flips:
            flip_wins = sum(1 for t in flips if t.pnl > 0)
            print(f"")
            print(f"  Flips:          {len(flips)} ({flip_wins} profitable)")
    print(f"{'='*60}")


def main():
    os.makedirs("data", exist_ok=True)
    candles = download_candles(SYMBOL, "30m", 1500)

    if len(candles) < 100:
        print("ERROR: Not enough data")
        return

    # Fetch Coinglass data
    cg_data = fetch_coinglass_oi()
    oi_filters = build_oi_filter(cg_data, candles)

    days = len(candles) * 30 / 60 / 24
    print(f"\nData: {len(candles)} candles = {days:.0f} days")
    print(f"Config: {LEVERAGE}x leverage, {MARGIN_PCT*100:.0f}% margin, SL -50%")
    print(f"TPs: +15%(10%) -> +50%(60%) -> +300%(rest) | Flip on reverse")
    print(f"Filters: Coinglass OI + L/S ratio + liquidation")

    # Test WITHOUT Coinglass filter
    print(f"\n--- Without Coinglass filter ---")
    trades1, curve1, sigs1 = run_backtest(candles, oi_filters=None)
    print_results(trades1, curve1, sigs1, len(candles))

    # Test WITH Coinglass filter
    print(f"\n--- With Coinglass filter ---")
    trades2, curve2, sigs2 = run_backtest(candles, oi_filters=oi_filters)
    print_results(trades2, curve2, sigs2, len(candles))


if __name__ == "__main__":
    main()
