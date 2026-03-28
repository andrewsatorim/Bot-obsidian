"""Breakout+Flip Live Trading Bot.

Strategy: Breakout + Position Flip + Coinglass OI/Funding/LS filters
Exchange: OKX (paper or live)
Timeframe: 30m (checks on each candle close)

Setup:
    1. Copy .env.example to .env and fill in API keys
    2. Run: python scripts/live_bot.py

Environment variables (.env):
    BOT_EXCHANGE_API_KEY=your_okx_api_key
    BOT_EXCHANGE_API_SECRET=your_okx_api_secret
    BOT_EXCHANGE_PASSPHRASE=your_okx_passphrase
    BOT_COINGLASS_API_KEY=ce8e53d9a000432bbd0bafa1bc4e9171
    BOT_PAPER_TRADING=true
    BOT_ACCOUNT_EQUITY=10000
    BOT_TELEGRAM_BOT_TOKEN=optional
    BOT_TELEGRAM_CHAT_ID=optional
"""
from __future__ import annotations
import os, sys, time, json, logging
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import Settings
from app.analytics.feature_engine import FeatureEngine
from app.strategy.breakout import BreakoutStrategy
from app.feeds.coinglass_v4 import CoinglassV4
from app.models.enums import Direction

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("data/live_bot.log"),
    ]
)
logger = logging.getLogger("live_bot")

# ============ OKX API ============

OKX_BASE = "https://www.okx.com"

class OKXClient:
    """Minimal OKX API client for candles, positions, and orders."""

    def __init__(self, api_key: str, secret: str, passphrase: str, paper: bool = True):
        self.api_key = api_key
        self.secret = secret
        self.passphrase = passphrase
        self.paper = paper

    def _get(self, path, params=None):
        headers = {}
        if self.paper:
            headers["x-simulated-trading"] = "1"
        r = requests.get(f"{OKX_BASE}{path}", params=params, headers=headers, timeout=15)
        r.raise_for_status()
        return r.json()

    def get_candles(self, inst_id, bar="30m", limit=100):
        """Get recent candles."""
        data = self._get("/api/v5/market/candles", {
            "instId": inst_id, "bar": bar, "limit": str(limit)
        })
        candles = []
        for c in data.get("data", []):
            candles.append({
                "ts": int(c[0]), "open": float(c[1]), "high": float(c[2]),
                "low": float(c[3]), "close": float(c[4]),
                "vol": float(c[5]), "vol_ccy": float(c[7]) if len(c) > 7 else float(c[5]),
            })
        candles.sort(key=lambda x: x["ts"])
        return candles

    def get_oi(self, inst_id):
        """Get current open interest."""
        data = self._get("/api/v5/public/open-interest", {"instId": inst_id})
        for r in data.get("data", []):
            if isinstance(r, dict):
                return float(r.get("oiCcy", 0))
        return 0.0


# ============ POSITION TRACKER ============

class PositionTracker:
    """Tracks open positions and trailing stops."""

    def __init__(self, state_file: str = "data/positions.json"):
        self._file = state_file
        self.positions: dict[str, dict] = {}
        self._load()

    def _load(self):
        if Path(self._file).exists():
            try:
                with open(self._file) as f:
                    self.positions = json.load(f)
                logger.info("Loaded %d positions from state", len(self.positions))
            except Exception:
                self.positions = {}

    def save(self):
        Path(self._file).parent.mkdir(parents=True, exist_ok=True)
        with open(self._file, "w") as f:
            json.dump(self.positions, f, indent=2, default=str)

    def has_position(self, symbol: str) -> bool:
        return symbol in self.positions

    def get_position(self, symbol: str) -> dict | None:
        return self.positions.get(symbol)

    def open_position(self, symbol: str, direction: str, entry_price: float,
                      qty: float, sl: float, atr: float):
        self.positions[symbol] = {
            "direction": direction,
            "entry_price": entry_price,
            "qty": qty,
            "sl": sl,
            "atr": atr,
            "peak": entry_price,
            "opened_at": datetime.now(timezone.utc).isoformat(),
            "pnl": 0.0,
        }
        self.save()
        logger.info("OPENED %s %s @ %.2f qty=%.6f sl=%.2f",
                     direction, symbol, entry_price, qty, sl)

    def close_position(self, symbol: str, exit_price: float, reason: str) -> float:
        pos = self.positions.pop(symbol, None)
        if not pos:
            return 0.0
        if pos["direction"] == "LONG":
            pnl = (exit_price - pos["entry_price"]) * pos["qty"]
        else:
            pnl = (pos["entry_price"] - exit_price) * pos["qty"]
        self.save()
        logger.info("CLOSED %s %s @ %.2f -> %.2f PnL=%.2f reason=%s",
                     pos["direction"], symbol, pos["entry_price"], exit_price, pnl, reason)
        return pnl

    def update_trailing_stop(self, symbol: str, price: float, trail_atr: float):
        pos = self.positions.get(symbol)
        if not pos:
            return
        atr = pos["atr"]
        if pos["direction"] == "LONG":
            pos["peak"] = max(pos["peak"], price)
            new_sl = pos["peak"] - trail_atr * atr
            if new_sl > pos["sl"]:
                pos["sl"] = new_sl
        else:
            pos["peak"] = min(pos["peak"], price)
            new_sl = pos["peak"] + trail_atr * atr
            if new_sl < pos["sl"]:
                pos["sl"] = new_sl
        self.save()

    def check_sl(self, symbol: str, price: float) -> bool:
        pos = self.positions.get(symbol)
        if not pos:
            return False
        if pos["direction"] == "LONG" and price <= pos["sl"]:
            return True
        if pos["direction"] == "SHORT" and price >= pos["sl"]:
            return True
        return False


# ============ MAIN BOT ============

class LiveBot:
    def __init__(self):
        self.settings = Settings()
        self.fe = FeatureEngine()
        self.cg = CoinglassV4(self.settings.coinglass_api_key)
        self.okx = OKXClient(
            self.settings.exchange_api_key,
            self.settings.exchange_api_secret,
            self.settings.exchange_passphrase,
            self.settings.paper_trading,
        )
        self.tracker = PositionTracker()
        self.strategies: dict[str, BreakoutStrategy] = {}
        self.daily_pnl = 0.0
        self.daily_pnl_reset = datetime.now(timezone.utc).date()

        # Config
        self.margin_pct = 0.25
        self.leverage = 25
        self.trail_atr = 2.5
        self.max_daily_loss = self.settings.account_equity * self.settings.max_daily_loss_pct

        # Symbols to trade
        self.symbols = [
            {"name": "BTC", "inst_id": "BTC-USDT-SWAP", "ccxt": "BTC/USDT:USDT"},
            {"name": "ETH", "inst_id": "ETH-USDT-SWAP", "ccxt": "ETH/USDT:USDT"},
            {"name": "SOL", "inst_id": "SOL-USDT-SWAP", "ccxt": "SOL/USDT:USDT"},
            {"name": "ADA", "inst_id": "ADA-USDT-SWAP", "ccxt": "ADA/USDT:USDT"},
        ]

    def _build_bundles(self, candles, symbol):
        from app.models.market_data_bundle import MarketDataBundle
        from app.models.market_snapshot import MarketSnapshot

        hs = min(50, len(candles) - 1)
        bundles = []
        for i in range(hs, len(candles)):
            c = candles[i]
            price, vol = c["close"], c["vol_ccy"]
            sp = price * 0.0002
            snap = MarketSnapshot(
                symbol=symbol, price=price, volume=vol,
                bid=price - sp/2, ask=price + sp/2,
                timestamp=max(int(c["ts"]/1000), 1),
            )
            s = max(0, i - hs)
            ph = [candles[j]["close"] for j in range(s, i + 1)]
            vh = [candles[j]["vol_ccy"] for j in range(s, i + 1)]
            bundles.append(MarketDataBundle(
                market=snap, price_history=ph, volume_history=vh,
                oi_history=[0.0], funding_history=[0.0],
                liquidation_above=price * 1.02, liquidation_below=price * 0.98,
            ))
        return bundles

    def process_symbol(self, sym: dict):
        """Process one symbol: check SL, check signal, apply Coinglass filters."""
        name = sym["name"]
        inst_id = sym["inst_id"]
        ccxt_id = sym["ccxt"]

        # Get candles
        candles = self.okx.get_candles(inst_id, "30m", 100)
        if len(candles) < 55:
            logger.warning("[%s] Not enough candles: %d", name, len(candles))
            return

        price = candles[-1]["close"]

        # Update trailing stop
        if self.tracker.has_position(name):
            self.tracker.update_trailing_stop(name, price, self.trail_atr)

            # Check stop loss
            if self.tracker.check_sl(name, price):
                pnl = self.tracker.close_position(name, price, "TRAILING_STOP")
                self.daily_pnl += pnl
                logger.info("[%s] Trailing stop hit. Daily PnL: %.2f", name, self.daily_pnl)

        # Build features and generate signal
        if name not in self.strategies:
            self.strategies[name] = BreakoutStrategy(symbol=ccxt_id)

        bundles = self._build_bundles(candles, ccxt_id)
        if not bundles:
            return

        features = self.fe.build_features(bundles[-1])
        signal = self.strategies[name].generate_signal(features)

        if signal is None:
            return

        direction = signal.direction.value  # "LONG" or "SHORT"

        # ============ COINGLASS FILTERS ============
        passed, reasons = self.cg.check_entry_filters(name, direction)
        if not passed:
            logger.info("[%s] Signal %s REJECTED by Coinglass: %s",
                        name, direction, ", ".join(reasons))
            return

        # ============ DAILY LOSS LIMIT ============
        if self.daily_pnl < -self.max_daily_loss:
            logger.warning("[%s] Daily loss limit reached: %.2f", name, self.daily_pnl)
            return

        # ============ POSITION FLIP ============
        pos = self.tracker.get_position(name)
        if pos and pos["direction"] != direction:
            pnl = self.tracker.close_position(name, price, f"FLIP_TO_{direction}")
            self.daily_pnl += pnl

        # ============ OPEN POSITION ============
        if not self.tracker.has_position(name):
            atr = features.atr if features.atr > 0 else price * 0.01
            equity = self.settings.account_equity + self.daily_pnl
            margin = equity * self.margin_pct
            qty = margin * self.leverage / price

            if direction == "LONG":
                sl = price - atr
            else:
                sl = price + atr

            self.tracker.open_position(name, direction, price, qty, sl, atr)
            logger.info("[%s] ENTRY %s @ %.2f qty=%.6f margin=$%.2f [CG filters: OK]",
                         name, direction, price, qty, margin)

    def run_once(self):
        """Run one cycle across all symbols."""
        now = datetime.now(timezone.utc)
        logger.info("=" * 60)
        logger.info("Cycle at %s", now.strftime("%Y-%m-%d %H:%M:%S UTC"))

        # Reset daily PnL at midnight
        if now.date() != self.daily_pnl_reset:
            logger.info("Daily PnL reset: %.2f -> 0", self.daily_pnl)
            self.daily_pnl = 0.0
            self.daily_pnl_reset = now.date()

        for sym in self.symbols:
            try:
                self.process_symbol(sym)
            except Exception as e:
                logger.error("[%s] Error: %s", sym["name"], e, exc_info=True)
            time.sleep(1)  # Small delay between symbols

        # Summary
        positions = self.tracker.positions
        if positions:
            logger.info("Open positions: %s", ", ".join(
                f"{s}={p['direction']}@{p['entry_price']:.2f}" for s, p in positions.items()
            ))
        logger.info("Daily PnL: $%.2f", self.daily_pnl)

    def run(self):
        """Main loop — runs every 30 minutes aligned to candle close."""
        logger.info("=" * 60)
        logger.info("LIVE BOT STARTING")
        logger.info("Mode: %s", "PAPER" if self.settings.paper_trading else "LIVE")
        logger.info("Symbols: %s", [s["name"] for s in self.symbols])
        logger.info("Margin: %.0f%% | Leverage: %dx | Trail: %.1f ATR",
                     self.margin_pct * 100, self.leverage, self.trail_atr)
        logger.info("Coinglass filters: OI + Funding + L/S ratio")
        logger.info("=" * 60)

        while True:
            try:
                self.run_once()
            except KeyboardInterrupt:
                logger.info("Bot stopped by user")
                break
            except Exception as e:
                logger.error("Cycle error: %s", e, exc_info=True)

            # Wait until next 30min candle close
            now = time.time()
            next_30m = ((now // 1800) + 1) * 1800 + 5  # 5 sec after candle close
            wait = max(next_30m - now, 10)
            logger.info("Next cycle in %.0f seconds (%.1f min)", wait, wait / 60)
            try:
                time.sleep(wait)
            except KeyboardInterrupt:
                logger.info("Bot stopped by user")
                break


if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    bot = LiveBot()

    if "--once" in sys.argv:
        bot.run_once()
    else:
        bot.run()
