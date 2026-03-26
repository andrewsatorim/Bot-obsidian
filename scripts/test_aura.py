"""Aura V14 backtest with Coinglass HOBBYIST API + confirmation filters.

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
CG_BASE = "https://open-api-v3.coinglass.com"  # HOBBYIST uses V3
CG_KEY = "ce8e53d9a000432bbd0bafa1bc4e9171"  # HOBBYIST plan key
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
    headers = {"accept": "application/json", "coinglassSecret": CG_KEY}
    resp = requests.get(f"{CG_BASE}{path}", headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") not in ("0", 0) and data.get("success") is not True:
        print(f"  CG err: {data.get('msg', data.get('code', 'unknown'))}", end="", flush=True)
    return data


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
    """Fetch data from Coinglass API (HOBBYIST plan)."""
    print("Fetching Coinglass...", end=" ", flush=True)
    result = {"ls_data": [], "oi_data": [], "taker_data": []}

    # Try multiple endpoint formats
    endpoints_ls = [
        ("/api/futures/globalLongShortAccountRatio/chart", {"symbol": "BTC", "interval": "1h", "limit": "500"}),
        ("/api/futures/globalLongShortAccountRatio", {"symbol": "BTC", "timeType": "2"}),
    ]
    for path, params in endpoints_ls:
        try:
            data = cg_get(path, params)
            ls = data.get("data", [])
            if isinstance(ls, list) and len(ls) > 0:
                result["ls_data"] = ls
                print(f"ls({len(ls)})", end="..", flush=True)
                break
        except Exception as e:
            print(f"ls_err:{type(e).__name__}", end="..", flush=True)

    # OI
    endpoints_oi = [
        ("/api/futures/openInterest/chart", {"symbol": "BTC", "interval": "2", "limit": "500"}),
        ("/api/futures/openInterest/ohlc-history", {"symbol": "BTC", "interval": "1h", "limit": "500"}),
    ]
    for path, params in endpoints_oi:
        try:
            data = cg_get(path, params)
            oi = data.get("data", [])
            if isinstance(oi, list) and len(oi) > 0:
                result["oi_data"] = oi
                print(f"oi({len(oi)})", end="..", flush=True)
                break
        except Exception as e:
            print(f"oi_err:{type(e).__name__}", end="..", flush=True)

    # Liquidation
    endpoints_liq = [
        ("/api/futures/liquidation/chart", {"symbol": "BTC", "timeType": "2"}),
        ("/api/futures/liquidation_chart", {"symbol": "BTC", "timeType": "2"}),
    ]
    for path, params in endpoints_liq:
        try:
            data = cg_get(path, params)
            liq = data.get("data", [])
            if liq:
                result["liq_data"] = liq
                print(f"liq", end="..", flush=True)
                break
        except Exception as e:
            print(f"liq_err:{type(e).__name__}", end="..", flush=True)

    # Funding
    try:
        data = cg_get("/api/futures/funding/current", {"symbol": "BTC"})
        fund = data.get("data", [])
        if fund:
            result["funding"] = fund
            print(f"fund", end="..", flush=True)
    except Exception as e:
        print(f"fund_err:{type(e).__name__}", end="..", flush=True)

    print(" done")

    # Debug: show what we got
    for k, v in result.items():
        if isinstance(v, list):
            print(f"  {k}: {len(v)} records", end="")
            if v and isinstance(v[0], dict):
                print(f" keys={list(v[0].keys())[:5]}")
            else:
                print()
    return result


def build_cg_filter(cg_data, candles):
    """Build per-candle filter from Coinglass data."""
    ls_map = {}
    for r in cg_data.get("ls_data", []):
        if isinstance(r, dict):
            ts = int(r.get("createTime", r.get("time", r.get("t", r.get("ts", 0)))))
            long_r = float(r.get("longRate", r.get("longAccount", r.get("longRatio", 0.5))))
            short_r = float(r.get("shortRate", r.get("shortAccount", r.get("shortRatio", 0.5))))
            if ts > 0:
                bucket = ts // (3600*1000) * (3600*1000)
                ls_map[bucket] = {"long": long_r, "short": short_r}
        elif isinstance(r, list) and len(r) >= 3:
            ts = int(r[0])
            bucket = ts // (3600*1000) * (3600*1000)
            ls_map[bucket] = {"long": float(r[1]), "short": float(r[2])}

    oi_map = {}
    for r in cg_data.get("oi_data", []):
        if isinstance(r, dict):
            ts = int(r.get("createTime", r.get("t", r.get("ts", r.get("time", 0)))))
            oi_val = float(r.get("openInterest", r.get("oi", r.get("o", r.get("value", 0)))))
            if ts > 0 and oi_val > 0:
                bucket = ts // (3600*1000) * (3600*1000)
                oi_map[bucket] = oi_val
        elif isinstance(r, list) and len(r) >= 2:
            ts = int(r[0])
            oi_val = float(r[1])
            if oi_val > 0:
                bucket = ts // (3600*1000) * (3600*1000)
                oi_map[bucket] = oi_val

    filters = {}
    prev_oi = 0
    for idx, c in enumerate(candles):
        ts = c[0]
        bucket_1h = ts // (3600*1000) * (3600*1000)
        ls = ls_map.get(bucket_1h, {"long": 0.5, "short": 0.5})
        oi = oi_map.get(bucket_1h, 0)
        oi_change = (oi - prev_oi) / prev_oi if prev_oi > 0 and oi > 0 else 0
        if oi > 0:
            prev_oi = oi
        filters[idx] = {
            "long_pct": ls["long"], "short_pct": ls["short"],
            "oi": oi, "oi_change": oi_change,
            "has_ls": bucket_1h in ls_map, "has_oi": oi > 0,
        }

    has_ls = sum(1 for f in filters.values() if f["has_ls"])
    has_oi = sum(1 for f in filters.values() if f["has_oi"])
    print(f"Coinglass coverage: LS={has_ls}/{len(candles)} OI={has_oi}/{len(candles)}")
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


def should_skip(signal, idx, cg_f, prev_dirs):
    new_dir = "LONG" if signal == "BUY" else "SHORT"
    # B1: 2 consecutive candles in direction
    if len(prev_dirs) >= 2:
        if new_dir == "LONG" and not (prev_dirs[-1] > 0 and prev_dirs[-2] > 0):
            return True
        if new_dir == "SHORT" and not (prev_dirs[-1] < 0 and prev_dirs[-2] < 0):
            return True
    # B2: Coinglass L/S
    if cg_f and idx in cg_f:
        f = cg_f[idx]
        if f["has_ls"]:
            if new_dir == "LONG" and f["long_pct"] > 0.60:
                return True
            if new_dir == "SHORT" and f["short_pct"] > 0.60:
                return True
        if f["has_oi"] and f["oi_change"] < -0.05:
            return True
    return False


def run_backtest(candles, cg_f=None, sl_pct=-0.25, margin_pct=0.15, use_confirm=True):
    aura = AuraV14()
    equity = 10_000.0
    curve = [equity]
    trades: list[Trade] = []
    pos: Position | None = None
    sigs = 0
    filt = 0
    prev_dirs: list[float] = []

    for idx, c in enumerate(candles):
        ts, o, h, l, close, vc, vu = c
        prev_dirs.append(close - o)
        if len(prev_dirs) > 10: prev_dirs = prev_dirs[-10:]

        signal = aura.update(o, h, l, close, vu)

        if pos is not None:
            if pos.direction == "LONG":
                pb = (h - pos.entry_price) * pos.quantity
                pw = (l - pos.entry_price) * pos.quantity
            else:
                pb = (pos.entry_price - l) * pos.quantity
                pw = (pos.entry_price - h) * pos.quantity
            margin = pos.entry_price * pos.initial_quantity / LEVERAGE
            ppb = pb / margin if margin > 0 else 0
            ppw = pw / margin if margin > 0 else 0

            if ppw <= sl_pct:
                t = pw + pos.realized_pnl
                fee = close * pos.quantity * FEE_RATE
                equity += t - fee
                trades.append(Trade(pos.direction, pos.entry_price, close, t-fee, sum(pos.tp_hit), f"SL({sl_pct:.0%})", 0, idx))
                pos = None; curve.append(equity); continue

            for i in range(len(TP_LEVELS)-1, -1, -1):
                tp_pct, cl_pct = TP_LEVELS[i]
                if pos.tp_hit[i]: continue
                if ppb >= tp_pct:
                    pos.tp_hit[i] = True
                    if cl_pct >= 0.99:
                        t = pb + pos.realized_pnl
                        fee = close * pos.quantity * FEE_RATE
                        equity += t - fee
                        trades.append(Trade(pos.direction, pos.entry_price, close, t-fee, sum(pos.tp_hit), f"TP{i+1}", 0, idx))
                        pos = None
                    else:
                        cq = pos.initial_quantity * cl_pct
                        cq = min(cq, pos.quantity)
                        if pos.direction == "LONG": pp = (close - pos.entry_price) * cq
                        else: pp = (pos.entry_price - close) * cq
                        fee = close * cq * FEE_RATE
                        pos.quantity -= cq
                        pos.realized_pnl += pp - fee
                        if pos.quantity <= 0.0001:
                            equity += pos.realized_pnl
                            trades.append(Trade(pos.direction, pos.entry_price, close, pos.realized_pnl, sum(pos.tp_hit), f"TP{i+1}", 0, idx))
                            pos = None
                    break

        if signal is not None:
            sigs += 1
            nd = "LONG" if signal == "BUY" else "SHORT"
            if use_confirm and should_skip(signal, idx, cg_f, prev_dirs):
                filt += 1; curve.append(equity); continue
            if pos is not None and pos.direction != nd:
                if pos.direction == "LONG": pnl = (close - pos.entry_price) * pos.quantity
                else: pnl = (pos.entry_price - close) * pos.quantity
                fee = close * pos.quantity * FEE_RATE
                t = pnl + pos.realized_pnl - fee
                equity += t
                trades.append(Trade(pos.direction, pos.entry_price, close, t, sum(pos.tp_hit), "FLIP", 0, idx))
                pos = None
            if pos is None:
                m = equity * margin_pct
                n = m * LEVERAGE
                q = n / close if close > 0 else 0
                equity -= n * FEE_RATE
                pos = Position(nd, close, q, q, m)
        curve.append(equity)

    if pos is not None:
        if pos.direction == "LONG": pnl = (candles[-1][4] - pos.entry_price) * pos.quantity
        else: pnl = (pos.entry_price - candles[-1][4]) * pos.quantity
        fee = candles[-1][4] * pos.quantity * FEE_RATE
        t = pnl + pos.realized_pnl - fee
        equity += t
        trades.append(Trade(pos.direction, pos.entry_price, candles[-1][4], t, sum(pos.tp_hit), "END", 0, len(candles)-1))
        curve[-1] = equity

    return trades, curve, sigs, filt


def main():
    os.makedirs("data", exist_ok=True)
    candles = download_candles(SYMBOL, "30m", 1500)
    if len(candles) < 100:
        print("ERROR: Not enough data"); return

    cg = fetch_coinglass()
    cg_f = build_cg_filter(cg, candles)

    days = len(candles) * 30 / 60 / 24
    print(f"\nData: {len(candles)} candles = {days:.0f} days")

    configs = [
        {"name": "A) No filter, SL-25%, 15%",    "sl": -0.25, "m": 0.15, "cg": None, "cf": False},
        {"name": "B) Confirm, SL-25%, 15%",       "sl": -0.25, "m": 0.15, "cg": None, "cf": True},
        {"name": "C) CG+Confirm, SL-25%, 15%",    "sl": -0.25, "m": 0.15, "cg": cg_f, "cf": True},
        {"name": "D) CG+Confirm, SL-25%, 10%",    "sl": -0.25, "m": 0.10, "cg": cg_f, "cf": True},
        {"name": "E) CG+Confirm, SL-25%, 7%",     "sl": -0.25, "m": 0.07, "cg": cg_f, "cf": True},
    ]

    print(f"\n{'='*90}")
    print(f"{'Config':<35} {'Sig':>4} {'Flt':>4} {'Trd':>4} {'WR':>6} {'PF':>7} {'Return':>8} {'MDD':>7} {'Equity':>10}")
    print(f"{'-'*90}")

    for cfg in configs:
        tr, cu, sg, ft = run_backtest(candles, cg_f=cfg["cg"], sl_pct=cfg["sl"], margin_pct=cfg["m"], use_confirm=cfg["cf"])
        n = len(tr)
        wr = sum(1 for t in tr if t.pnl > 0) / n * 100 if n else 0
        gp = sum(t.pnl for t in tr if t.pnl > 0)
        gl = abs(sum(t.pnl for t in tr if t.pnl < 0))
        pf = gp / gl if gl > 0 else float('inf')
        ret = (cu[-1] - 10000) / 10000 * 100
        pk = 10000; md = 0
        for eq in cu:
            if eq > pk: pk = eq
            dd = (pk - eq) / pk * 100
            if dd > md: md = dd
        pfs = f"{pf:.2f}" if pf < 100 else "inf"
        print(f"{cfg['name']:<35} {sg:>4} {ft:>4} {n:>4} {wr:>5.1f}% {pfs:>7} {ret:>+7.2f}% {md:>6.2f}% ${cu[-1]:>9.2f}")
        if cfg['name'].startswith('C)'):
            reasons = {}
            for t in tr:
                reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1
            print(f"    Exits: {reasons}")

    print(f"{'='*90}")


if __name__ == "__main__":
    main()
