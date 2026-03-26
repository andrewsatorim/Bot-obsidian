"""Aura V14 backtest — FIXED: PnL at trigger price, correct Coinglass header.

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
CG_KEY = os.environ.get("BOT_COINGLASS_API_KEY", "ce8e53d9a000432bbd0bafa1bc4e9171")
LEVERAGE = 40
FEE_RATE = 0.0006  # maker+taker average
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
    """Require 2 PRIOR candles in signal direction (not including current)."""
    nd = "LONG" if signal == "BUY" else "SHORT"
    if len(prev_dirs) < 3:  # need at least 2 prior + current
        return True
    # Check 2 prior candles (not current which is [-1])
    if nd == "LONG" and not (prev_dirs[-2] > 0 and prev_dirs[-3] > 0):
        return True
    if nd == "SHORT" and not (prev_dirs[-2] < 0 and prev_dirs[-3] < 0):
        return True
    return False

def run_backtest(candles, sl_pct=-0.25, margin_pct=0.15, use_confirm=True):
    aura = AuraV14()
    equity = 10_000.0
    curve = [equity]
    trades = []
    pos = None
    sigs = 0; filt = 0
    prev_dirs = []

    for idx, c in enumerate(candles):
        ts, o, h, l, close, vc, vu = c
        prev_dirs.append(close - o)
        if len(prev_dirs) > 10: prev_dirs = prev_dirs[-10:]
        signal = aura.update(o, h, l, close, vu)

        # --- CHECK TP/SL ---
        if pos is not None:
            margin = pos.entry_price * pos.initial_quantity / LEVERAGE

            # Calculate trigger prices for TP and SL
            if pos.direction == "LONG":
                sl_trigger = pos.entry_price * (1 + sl_pct / LEVERAGE * LEVERAGE)  # Simplified
                # SL check on LOW
                pnl_at_low = (l - pos.entry_price) * pos.quantity
                pnl_pct_low = pnl_at_low / margin if margin > 0 else 0
                # TP check on HIGH
                pnl_at_high = (h - pos.entry_price) * pos.quantity
                pnl_pct_high = pnl_at_high / margin if margin > 0 else 0
            else:
                pnl_at_low = (pos.entry_price - h) * pos.quantity  # worst for SHORT
                pnl_pct_low = pnl_at_low / margin if margin > 0 else 0
                pnl_at_high = (pos.entry_price - l) * pos.quantity  # best for SHORT
                pnl_pct_high = pnl_at_high / margin if margin > 0 else 0

            # SL: use worst-case price, PnL at SL trigger price (FIXED)
            if pnl_pct_low <= sl_pct:
                # Calculate exact SL trigger price
                sl_price_move = sl_pct * margin / pos.quantity if pos.quantity > 0 else 0
                if pos.direction == "LONG":
                    sl_price = pos.entry_price + sl_price_move
                else:
                    sl_price = pos.entry_price - sl_price_move
                sl_pnl = sl_pct * margin  # Exact PnL at SL = sl_pct * margin
                total = sl_pnl + pos.realized_pnl
                fee = abs(sl_price) * pos.quantity * FEE_RATE
                equity += total - fee
                trades.append(Trade(pos.direction, pos.entry_price, sl_price, total-fee, sum(pos.tp_hit), f"SL({sl_pct:.0%})", 0, idx))
                pos = None; curve.append(equity); continue

            # TPs: use best-case price, PnL at TP trigger price (FIXED)
            for i in range(len(TP_LEVELS)-1, -1, -1):
                tp_pct, cl_pct = TP_LEVELS[i]
                if pos.tp_hit[i]: continue
                if pnl_pct_high >= tp_pct:
                    pos.tp_hit[i] = True
                    # PnL at exact TP price
                    tp_pnl_per_unit = tp_pct * margin / pos.initial_quantity if pos.initial_quantity > 0 else 0
                    if cl_pct >= 0.99:
                        tp_total_pnl = tp_pct * margin + pos.realized_pnl
                        fee = close * pos.quantity * FEE_RATE
                        equity += tp_total_pnl - fee
                        trades.append(Trade(pos.direction, pos.entry_price, close, tp_total_pnl-fee, sum(pos.tp_hit), f"TP{i+1}", 0, idx))
                        pos = None
                    else:
                        cq = pos.initial_quantity * cl_pct
                        cq = min(cq, pos.quantity)
                        partial_pnl = tp_pnl_per_unit * cq
                        fee = close * cq * FEE_RATE
                        pos.quantity -= cq
                        pos.realized_pnl += partial_pnl - fee
                        if pos.quantity <= 0.0001:
                            equity += pos.realized_pnl
                            trades.append(Trade(pos.direction, pos.entry_price, close, pos.realized_pnl, sum(pos.tp_hit), f"TP{i+1}", 0, idx))
                            pos = None
                    break

        # --- SIGNAL ---
        if signal is not None:
            sigs += 1
            nd = "LONG" if signal == "BUY" else "SHORT"
            if use_confirm and should_skip(signal, prev_dirs):
                filt += 1; curve.append(equity); continue
            # FLIP
            if pos is not None and pos.direction != nd:
                if pos.direction == "LONG": pnl = (close - pos.entry_price) * pos.quantity
                else: pnl = (pos.entry_price - close) * pos.quantity
                fee = close * pos.quantity * FEE_RATE
                t = pnl + pos.realized_pnl - fee
                equity += t
                trades.append(Trade(pos.direction, pos.entry_price, close, t, sum(pos.tp_hit), "FLIP", 0, idx))
                pos = None
            # OPEN
            if pos is None and equity > 0:
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
    if len(candles) < 100: print("ERROR: Not enough data"); return
    days = len(candles) * 30 / 60 / 24
    print(f"\nData: {len(candles)} candles = {days:.0f} days")

    configs = [
        {"name": "A) No filter, SL-25%, 15%",    "sl": -0.25, "m": 0.15, "cf": False},
        {"name": "B) Confirm, SL-25%, 15%",       "sl": -0.25, "m": 0.15, "cf": True},
        {"name": "C) Confirm, SL-25%, 10%",       "sl": -0.25, "m": 0.10, "cf": True},
        {"name": "D) Confirm, SL-25%, 7%",        "sl": -0.25, "m": 0.07, "cf": True},
        {"name": "E) Confirm, SL-50%, 15%",       "sl": -0.50, "m": 0.15, "cf": True},
        {"name": "F) Confirm, SL-50%, 7%",        "sl": -0.50, "m": 0.07, "cf": True},
    ]

    print(f"\n{'='*90}")
    print(f"{'Config':<35} {'Sig':>4} {'Flt':>4} {'Trd':>4} {'WR':>6} {'PF':>7} {'Return':>8} {'MDD':>7} {'Equity':>10}")
    print(f"{'-'*90}")

    for cfg in configs:
        tr, cu, sg, ft = run_backtest(candles, sl_pct=cfg["sl"], margin_pct=cfg["m"], use_confirm=cfg["cf"])
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
        # Show exit distribution for best config
        if cfg['name'].startswith('B)'):
            reasons = {}
            for t in tr: reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1
            print(f"    Exits: {reasons}")
            if tr:
                best = max(tr, key=lambda t: t.pnl)
                worst = min(tr, key=lambda t: t.pnl)
                print(f"    Best:  ${best.pnl:+.2f} ({best.direction}->{best.exit_reason})")
                print(f"    Worst: ${worst.pnl:+.2f} ({worst.direction}->{worst.exit_reason})")
    print(f"{'='*90}")
    print(f"\nFixes applied:")
    print(f"  1. Wilder's RMA for RSI/ADX/ATR (matches Pine Script)")
    print(f"  2. Alpha line init from first valid bar (was 0.0)")
    print(f"  3. PnL at trigger price, not close (unbiased backtest)")
    print(f"  4. MFI skips equal TP bars")
    print(f"  5. Confirmation filter uses 2 PRIOR candles (not current)")
    print(f"  6. Fee rate 0.06% (realistic maker+taker avg)")

if __name__ == "__main__":
    main()
