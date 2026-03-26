"""Aura V14 backtest with Coinglass V4 API + confirmation filters.

Fixes:
- Coinglass API upgraded from V3 to V4 (correct endpoints)
- Added confirmation filter: skip signals where ADX < 35
- Added consecutive candles filter: 2 candles same direction before entry
- SL: -25% on margin

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
CG_BASE = "https://open-api-v4.coinglass.com"  # V4!
CG_KEY = "7abff9b1c52e41ddaff0d72ff2a8da09"
LEVERAGE = 40
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


def cg_get(path, params=None):
    headers = {"accept": "application/json", "CG-API-KEY": CG_KEY}
    resp = requests.get(f"{CG_BASE}{path}", headers=headers, params=params, timeout=15)
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
            all_c.append([int(c[0]), float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5]), float(c[7])])
        after = candles[-1][0]
        print(f"{len(all_c)}", end="..", flush=True)
        time.sleep(0.2)
    all_c.sort(key=lambda c: c[0])
    seen = set()
    unique = [c for c in all_c if c[0] not in seen and not seen.add(c[0])]
    print(f" total={len(unique)}")
    return unique


def fetch_coinglass():
    """Fetch data from Coinglass V4 API."""
    print("Fetching Coinglass V4...", end=" ", flush=True)
    result = {"ls_data": [], "oi_data": []}

    # Long/Short Account Ratio
    try:
        data = cg_get("/api/futures/globalLongShortAccountRatio/history", {
            "symbol": "BTC", "exchange": "OKX", "interval": "1h", "limit": "500",
        })
        ls = data.get("data", [])
        if isinstance(ls, list):
            result["ls_data"] = ls
            print(f"ls({len(ls)})", end="..", flush=True)
    except Exception as e:
        print(f"ls_err:{e}", end="..", flush=True)

    # OI OHLC History
    try:
        data = cg_get("/api/futures/openInterest/ohlc-history", {
            "symbol": "BTC", "interval": "30m", "limit": "500",
        })
        oi = data.get("data", [])
        if isinstance(oi, list):
            result["oi_data"] = oi
            print(f"oi({len(oi)})", end="..", flush=True)
    except Exception as e:
        print(f"oi_err:{e}", end="..", flush=True)

    # Taker Buy/Sell (long/short pressure)
    try:
        data = cg_get("/api/futures/aggregated-taker-buy-sell-volume/history", {
            "symbol": "BTC", "interval": "30m", "limit": "500",
        })
        taker = data.get("data", [])
        if isinstance(taker, list):
            result["taker_data"] = taker
            print(f"taker({len(taker)})", end="..", flush=True)
    except Exception as e:
        print(f"taker_err:{e}", end="..", flush=True)

    print(" done")
    return result


def build_cg_filter(cg_data, candles):
    """Build per-candle filter from Coinglass data."""
    # L/S ratio lookup
    ls_map = {}
    for r in cg_data.get("ls_data", []):
        if isinstance(r, dict):
            ts = int(r.get("time", r.get("t", r.get("ts", 0))))
            long_pct = float(r.get("longRate", r.get("longAccount", 0.5)))
            short_pct = float(r.get("shortRate", r.get("shortAccount", 0.5)))
            if ts > 0:
                bucket = ts // (3600*1000) * (3600*1000)  # 1h buckets
                ls_map[bucket] = {"long": long_pct, "short": short_pct}

    # OI lookup
    oi_map = {}
    for r in cg_data.get("oi_data", []):
        if isinstance(r, dict):
            ts = int(r.get("t", r.get("ts", r.get("time", 0))))
            oi_val = float(r.get("o", r.get("oi", r.get("openInterest", 0))))
            if ts > 0 and oi_val > 0:
                bucket = ts // (30*60*1000) * (30*60*1000)
                oi_map[bucket] = oi_val

    # Taker buy/sell lookup
    taker_map = {}
    for r in cg_data.get("taker_data", []):
        if isinstance(r, dict):
            ts = int(r.get("t", r.get("ts", r.get("time", 0))))
            buy = float(r.get("buyVolume", r.get("buy", 0)))
            sell = float(r.get("sellVolume", r.get("sell", 0)))
            if ts > 0:
                bucket = ts // (30*60*1000) * (30*60*1000)
                total = buy + sell
                taker_map[bucket] = buy / total if total > 0 else 0.5

    filters = {}
    prev_oi = 0
    for idx, c in enumerate(candles):
        ts = c[0]
        bucket_30m = ts // (30*60*1000) * (30*60*1000)
        bucket_1h = ts // (3600*1000) * (3600*1000)

        ls = ls_map.get(bucket_1h, {"long": 0.5, "short": 0.5})
        oi = oi_map.get(bucket_30m, 0)
        taker_buy_pct = taker_map.get(bucket_30m, 0.5)

        oi_change = 0.0
        if prev_oi > 0 and oi > 0:
            oi_change = (oi - prev_oi) / prev_oi
        if oi > 0:
            prev_oi = oi

        filters[idx] = {
            "long_pct": ls["long"],
            "short_pct": ls["short"],
            "oi": oi,
            "oi_change": oi_change,
            "taker_buy_pct": taker_buy_pct,
            "has_ls": bucket_1h in ls_map,
            "has_oi": oi > 0,
            "has_taker": bucket_30m in taker_map,
        }

    has_ls = sum(1 for f in filters.values() if f["has_ls"])
    has_oi = sum(1 for f in filters.values() if f["has_oi"])
    has_taker = sum(1 for f in filters.values() if f["has_taker"])
    print(f"Coinglass coverage: LS={has_ls}/{len(candles)} OI={has_oi}/{len(candles)} Taker={has_taker}/{len(candles)}")
    return filters


@dataclass
class Position:
    direction: str
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


def should_skip_signal(signal, idx, cg_filters, candles, prev_directions):
    """Confirmation filter: skip weak signals.

    Filter B1: Consecutive direction — need 2 candles moving in signal direction
    Filter B2: Coinglass L/S ratio — don't enter crowded side
    Filter B3: Coinglass taker pressure — taker flow must support direction
    Filter B4: Coinglass OI change — skip if OI crashing (>5%)
    """
    new_dir = "LONG" if signal == "BUY" else "SHORT"

    # B1: Need 2 consecutive candles in same direction
    if len(prev_directions) >= 2:
        if new_dir == "LONG" and not (prev_directions[-1] > 0 and prev_directions[-2] > 0):
            return True  # Price wasn't rising for 2 candles
        if new_dir == "SHORT" and not (prev_directions[-1] < 0 and prev_directions[-2] < 0):
            return True  # Price wasn't falling for 2 candles

    # Coinglass filters (only if data available)
    if cg_filters and idx in cg_filters:
        f = cg_filters[idx]

        # B2: L/S ratio filter
        if f["has_ls"]:
            if new_dir == "LONG" and f["long_pct"] > 0.60:
                return True  # Too many longs = crowded
            if new_dir == "SHORT" and f["short_pct"] > 0.60:
                return True  # Too many shorts = crowded

        # B3: Taker pressure
        if f["has_taker"]:
            if new_dir == "LONG" and f["taker_buy_pct"] < 0.45:
                return True  # Sellers dominating = don't long
            if new_dir == "SHORT" and f["taker_buy_pct"] > 0.55:
                return True  # Buyers dominating = don't short

        # B4: OI crash filter
        if f["has_oi"] and f["oi_change"] < -0.05:
            return True  # OI crashing = unstable

    return False


def run_backtest(candles, cg_filters=None, sl_pct=-0.25, margin_pct=0.15, use_confirm=True):
    aura = AuraV14()
    equity = 10_000.0
    equity_curve = [equity]
    trades: list[Trade] = []
    position: Position | None = None
    signals_count = 0
    filtered_count = 0
    prev_directions: list[float] = []  # Track candle direction

    for idx, c in enumerate(candles):
        ts, o, h, l, close, vol_contracts, vol_usdt = c

        # Track candle direction for confirmation filter
        prev_directions.append(close - o)
        if len(prev_directions) > 10:
            prev_directions = prev_directions[-10:]

        signal = aura.update(o, h, l, close, vol_usdt)

        # --- CHECK TP + SL ---
        if position is not None:
            if position.direction == "LONG":
                pnl_best = (h - position.entry_price) * position.quantity
                pnl_close = (close - position.entry_price) * position.quantity
                pnl_worst = (l - position.entry_price) * position.quantity
            else:
                pnl_best = (position.entry_price - l) * position.quantity
                pnl_close = (position.entry_price - close) * position.quantity
                pnl_worst = (position.entry_price - h) * position.quantity

            margin = position.entry_price * position.initial_quantity / LEVERAGE
            pnl_pct_best = pnl_best / margin if margin > 0 else 0
            pnl_pct_worst = pnl_worst / margin if margin > 0 else 0

            # SL
            if pnl_pct_worst <= sl_pct:
                total_pnl = pnl_worst + position.realized_pnl
                fee = close * position.quantity * FEE_RATE
                equity += total_pnl - fee
                trades.append(Trade(position.direction, position.entry_price, close, total_pnl - fee, sum(position.tp_hit), f"SL({sl_pct:.0%})", 0, idx))
                position = None
                equity_curve.append(equity)
                continue

            # TPs (check on best price)
            for i in range(len(TP_LEVELS) - 1, -1, -1):
                tp_pct, close_pct = TP_LEVELS[i]
                if position.tp_hit[i]:
                    continue
                if pnl_pct_best >= tp_pct:
                    position.tp_hit[i] = True
                    if close_pct >= 0.99:
                        total_pnl = pnl_best + position.realized_pnl
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

        # --- SIGNAL ---
        if signal is not None:
            signals_count += 1
            new_dir = "LONG" if signal == "BUY" else "SHORT"

            # Confirmation filter
            if use_confirm and should_skip_signal(signal, idx, cg_filters, candles, prev_directions):
                filtered_count += 1
                equity_curve.append(equity)
                continue

            # FLIP
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

            # OPEN
            if position is None:
                margin = equity * margin_pct
                notional = margin * LEVERAGE
                qty = notional / close if close > 0 else 0
                equity -= notional * FEE_RATE
                position = Position(direction=new_dir, entry_price=close, quantity=qty, initial_quantity=qty, margin=margin)

        equity_curve.append(equity)

    # Force close
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

    return trades, equity_curve, signals_count, filtered_count


def main():
    os.makedirs("data", exist_ok=True)
    candles = download_candles(SYMBOL, "30m", 1500)
    if len(candles) < 100:
        print("ERROR: Not enough data")
        return

    cg_data = fetch_coinglass()
    cg_filters = build_cg_filter(cg_data, candles)

    days = len(candles) * 30 / 60 / 24
    print(f"\nData: {len(candles)} candles = {days:.0f} days")
    print(f"TPs: +15%(10%) -> +50%(60%) -> +300%(rest) | Flip on reverse")

    configs = [
        {"name": "A) No filter, SL-50%, 15%",    "sl": -0.50, "m": 0.15, "cg": None,       "confirm": False},
        {"name": "B) Confirm only, SL-25%, 15%",  "sl": -0.25, "m": 0.15, "cg": None,       "confirm": True},
        {"name": "C) CG only, SL-25%, 15%",       "sl": -0.25, "m": 0.15, "cg": cg_filters, "confirm": False},
        {"name": "D) CG+Confirm, SL-25%, 15%",    "sl": -0.25, "m": 0.15, "cg": cg_filters, "confirm": True},
        {"name": "E) CG+Confirm, SL-25%, 10%",    "sl": -0.25, "m": 0.10, "cg": cg_filters, "confirm": True},
        {"name": "F) CG+Confirm, SL-25%, 7%",     "sl": -0.25, "m": 0.07, "cg": cg_filters, "confirm": True},
    ]

    print(f"\n{'='*90}")
    print(f"{'Config':<35} {'Sig':>4} {'Flt':>4} {'Trd':>4} {'WR':>6} {'PF':>7} {'Return':>8} {'MDD':>7} {'Equity':>10}")
    print(f"{'-'*90}")

    for cfg in configs:
        trades, curve, sigs, filt = run_backtest(candles, cg_filters=cfg["cg"], sl_pct=cfg["sl"], margin_pct=cfg["m"], use_confirm=cfg["confirm"])
        n = len(trades)
        wr = sum(1 for t in trades if t.pnl > 0) / n * 100 if n else 0
        gp = sum(t.pnl for t in trades if t.pnl > 0)
        gl = abs(sum(t.pnl for t in trades if t.pnl < 0))
        pf = gp / gl if gl > 0 else float('inf')
        ret = (curve[-1] - 10000) / 10000 * 100
        peak = 10000; mdd = 0
        for eq in curve:
            if eq > peak: peak = eq
            dd = (peak - eq) / peak * 100
            if dd > mdd: mdd = dd
        pf_s = f"{pf:.2f}" if pf < 100 else "inf"
        print(f"{cfg['name']:<35} {sigs:>4} {filt:>4} {n:>4} {wr:>5.1f}% {pf_s:>7} {ret:>+7.2f}% {mdd:>6.2f}% ${curve[-1]:>9.2f}")

        # Show exit distribution for best config
        if cfg["name"].startswith("D)"):
            reasons = {}
            for t in trades:
                reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1
            print(f"    Exits: {reasons}")

    print(f"{'='*90}")


if __name__ == "__main__":
    main()
