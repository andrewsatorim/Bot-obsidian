"""Aura V14 backtest — limit orders + loss cooldown filter.

Usage: python scripts/test_aura.py
"""
from __future__ import annotations
import json, os, sys, time
from dataclasses import dataclass, field
import requests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.strategy.aura_v14 import AuraV14

SYMBOL = "BTC-USDT-SWAP"
BASE_URL = "https://www.okx.com"
LEVERAGE = 40

TP_LEVELS = [(0.15, 0.10), (0.50, 0.60), (3.00, 1.00)]

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
        if after: params["after"] = after
        data = okx_get("/api/v5/market/candles", params)
        candles = data.get("data", [])
        if not candles: break
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

@dataclass
class Position:
    direction: str
    entry_price: float
    quantity: float
    initial_quantity: float
    margin: float
    tp_hit: list[bool] = field(default_factory=lambda: [False]*3)
    realized_pnl: float = 0.0

@dataclass
class Trade:
    direction: str; entry_price: float; exit_price: float; pnl: float
    tp_hits: int; exit_reason: str; entry_idx: int; exit_idx: int

def should_skip(signal, prev_dirs):
    """Require 2 PRIOR candles in signal direction."""
    nd = "LONG" if signal == "BUY" else "SHORT"
    if len(prev_dirs) < 3:
        return True
    if nd == "LONG" and not (prev_dirs[-2] > 0 and prev_dirs[-3] > 0):
        return True
    if nd == "SHORT" and not (prev_dirs[-2] < 0 and prev_dirs[-3] < 0):
        return True
    return False

def run_backtest(candles, sl_pct=-0.25, margin_pct=0.15, fee_rate=0.0006,
                 use_confirm=True, skip_after_loss=False):
    aura = AuraV14()
    equity = 10_000.0
    curve = [equity]
    trades = []
    pos = None
    sigs = 0; filt = 0
    prev_dirs = []
    last_trade_loss = False  # Track if last trade was a loss

    for idx, c in enumerate(candles):
        ts, o, h, l, close, vc, vu = c
        prev_dirs.append(close - o)
        if len(prev_dirs) > 10: prev_dirs = prev_dirs[-10:]
        signal = aura.update(o, h, l, close, vu)

        # --- CHECK TP/SL ---
        if pos is not None:
            margin = pos.entry_price * pos.initial_quantity / LEVERAGE
            if pos.direction == "LONG":
                pnl_at_low = (l - pos.entry_price) * pos.quantity
                pnl_at_high = (h - pos.entry_price) * pos.quantity
            else:
                pnl_at_low = (pos.entry_price - h) * pos.quantity
                pnl_at_high = (pos.entry_price - l) * pos.quantity
            pnl_pct_low = pnl_at_low / margin if margin > 0 else 0
            pnl_pct_high = pnl_at_high / margin if margin > 0 else 0

            # SL at trigger price
            if pnl_pct_low <= sl_pct:
                sl_pnl = sl_pct * margin
                total = sl_pnl + pos.realized_pnl
                if pos.direction == "LONG": sl_price = pos.entry_price + sl_pnl / pos.quantity
                else: sl_price = pos.entry_price - sl_pnl / pos.quantity
                fee = abs(sl_price) * pos.quantity * fee_rate
                equity += total - fee
                trades.append(Trade(pos.direction, pos.entry_price, sl_price, total-fee, sum(pos.tp_hit), f"SL({sl_pct:.0%})", 0, idx))
                last_trade_loss = True
                pos = None; curve.append(equity); continue

            # TPs at trigger price
            for i in range(len(TP_LEVELS)-1, -1, -1):
                tp_pct, cl_pct = TP_LEVELS[i]
                if pos.tp_hit[i]: continue
                if pnl_pct_high >= tp_pct:
                    pos.tp_hit[i] = True
                    tp_pnl_per_unit = tp_pct * margin / pos.initial_quantity if pos.initial_quantity > 0 else 0
                    if cl_pct >= 0.99:
                        tp_total = tp_pct * margin + pos.realized_pnl
                        fee = close * pos.quantity * fee_rate
                        equity += tp_total - fee
                        trades.append(Trade(pos.direction, pos.entry_price, close, tp_total-fee, sum(pos.tp_hit), f"TP{i+1}", 0, idx))
                        last_trade_loss = False
                        pos = None
                    else:
                        cq = min(pos.initial_quantity * cl_pct, pos.quantity)
                        partial = tp_pnl_per_unit * cq
                        fee = close * cq * fee_rate
                        pos.quantity -= cq
                        pos.realized_pnl += partial - fee
                        if pos.quantity <= 0.0001:
                            equity += pos.realized_pnl
                            trades.append(Trade(pos.direction, pos.entry_price, close, pos.realized_pnl, sum(pos.tp_hit), f"TP{i+1}", 0, idx))
                            last_trade_loss = False
                            pos = None
                    break

        # --- SIGNAL ---
        if signal is not None:
            sigs += 1
            nd = "LONG" if signal == "BUY" else "SHORT"

            # Filter 1: Confirmation (2 prior candles)
            if use_confirm and should_skip(signal, prev_dirs):
                filt += 1; curve.append(equity); continue

            # Filter 2: Skip after loss (new)
            if skip_after_loss and last_trade_loss:
                filt += 1
                last_trade_loss = False  # Reset — skip only 1 signal
                curve.append(equity); continue

            # FLIP
            if pos is not None and pos.direction != nd:
                if pos.direction == "LONG": pnl = (close - pos.entry_price) * pos.quantity
                else: pnl = (pos.entry_price - close) * pos.quantity
                fee = close * pos.quantity * fee_rate
                t = pnl + pos.realized_pnl - fee
                equity += t
                trades.append(Trade(pos.direction, pos.entry_price, close, t, sum(pos.tp_hit), "FLIP", 0, idx))
                last_trade_loss = t < 0
                pos = None

            # OPEN
            if pos is None and equity > 0:
                m = equity * margin_pct
                n = m * LEVERAGE
                q = n / close if close > 0 else 0
                equity -= n * fee_rate
                pos = Position(nd, close, q, q, m)
        curve.append(equity)

    if pos is not None:
        if pos.direction == "LONG": pnl = (candles[-1][4] - pos.entry_price) * pos.quantity
        else: pnl = (pos.entry_price - candles[-1][4]) * pos.quantity
        fee = candles[-1][4] * pos.quantity * 0.0006
        t = pnl + pos.realized_pnl - fee
        equity += t
        trades.append(Trade(pos.direction, pos.entry_price, candles[-1][4], t, sum(pos.tp_hit), "END", 0, len(candles)-1))
        curve[-1] = equity
    return trades, curve, sigs, filt

def main():
    os.makedirs("data", exist_ok=True)
    candles = download_candles(SYMBOL, "30m", 1500)
    if len(candles) < 100: print("ERROR: Not enough data"); return
    days = len(candles) * 30 / 60 / 24
    print(f"\nData: {len(candles)} candles = {days:.0f} days")

    configs = [
        # Taker fees (0.06%)
        {"name": "A) Taker, no filter, SL-25%, 15%",  "sl": -0.25, "m": 0.15, "fee": 0.0006, "cf": False, "sal": False},
        {"name": "B) Taker, confirm, SL-25%, 7%",      "sl": -0.25, "m": 0.07, "fee": 0.0006, "cf": True, "sal": False},
        {"name": "C) Taker, conf+skip, SL-25%, 7%",    "sl": -0.25, "m": 0.07, "fee": 0.0006, "cf": True, "sal": True},
        # Maker fees (0.02%)
        {"name": "D) Maker, no filter, SL-25%, 15%",   "sl": -0.25, "m": 0.15, "fee": 0.0002, "cf": False, "sal": False},
        {"name": "E) Maker, confirm, SL-25%, 15%",     "sl": -0.25, "m": 0.15, "fee": 0.0002, "cf": True, "sal": False},
        {"name": "F) Maker, conf+skip, SL-25%, 15%",   "sl": -0.25, "m": 0.15, "fee": 0.0002, "cf": True, "sal": True},
        {"name": "G) Maker, confirm, SL-25%, 10%",     "sl": -0.25, "m": 0.10, "fee": 0.0002, "cf": True, "sal": False},
        {"name": "H) Maker, conf+skip, SL-25%, 10%",   "sl": -0.25, "m": 0.10, "fee": 0.0002, "cf": True, "sal": True},
        {"name": "I) Maker, confirm, SL-25%, 7%",      "sl": -0.25, "m": 0.07, "fee": 0.0002, "cf": True, "sal": False},
        {"name": "J) Maker, conf+skip, SL-25%, 7%",    "sl": -0.25, "m": 0.07, "fee": 0.0002, "cf": True, "sal": True},
    ]

    print(f"\n{'='*95}")
    print(f"{'Config':<40} {'Sig':>4} {'Flt':>4} {'Trd':>4} {'WR':>6} {'PF':>7} {'Return':>8} {'MDD':>7} {'Equity':>10}")
    print(f"{'-'*95}")

    for cfg in configs:
        tr, cu, sg, ft = run_backtest(candles, sl_pct=cfg["sl"], margin_pct=cfg["m"],
                                      fee_rate=cfg["fee"], use_confirm=cfg["cf"],
                                      skip_after_loss=cfg["sal"])
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
        print(f"{cfg['name']:<40} {sg:>4} {ft:>4} {n:>4} {wr:>5.1f}% {pfs:>7} {ret:>+7.2f}% {md:>6.2f}% ${cu[-1]:>9.2f}")
        # Detail for best configs
        if cfg['name'].startswith(('F)', 'H)')):
            reasons = {}
            for t in tr: reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1
            print(f"    Exits: {reasons}")
            if tr:
                best = max(tr, key=lambda t: t.pnl)
                worst = min(tr, key=lambda t: t.pnl)
                print(f"    Best:  ${best.pnl:+.2f} ({best.direction}->{best.exit_reason})")
                print(f"    Worst: ${worst.pnl:+.2f} ({worst.direction}->{worst.exit_reason})")

    print(f"{'='*95}")
    print(f"\nKey: conf=confirmation filter, skip=skip signal after loss")
    print(f"Maker fee=0.02% (limit orders), Taker fee=0.06% (market orders)")

if __name__ == "__main__":
    main()
