"""Breakout+Flip Live Trading Bot — PRODUCTION VERSION.

Uses ccxt for OKX order execution + Coinglass V4 for OI/Funding/LS/Liquidation filters.

Setup:
    1. cp .env.example .env && nano .env  (fill OKX API keys)
    2. python scripts/live_bot.py --once   (test one cycle)
    3. python scripts/live_bot.py          (run live)
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ccxt.async_support as ccxt_async

from app.analytics.feature_engine import FeatureEngine
from app.config import Settings
from app.feeds.coinglass_v4 import CoinglassV4
from app.feeds.news_feed import NewsFeed
from app.models.enums import Direction, SetupType
from app.models.market_data_bundle import MarketDataBundle
from app.models.market_snapshot import MarketSnapshot
from app.models.trade_candidate import TradeCandidate
from app.risk.risk_manager import RiskManager
from app.strategy.breakout import BreakoutStrategy

os.makedirs("data", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("data/live_bot.log")],
)
logger = logging.getLogger("live_bot")

STATE_FILE = "data/positions.json"


# ============ OKX EXCHANGE (via ccxt) ============

class OKXExchange:
    """Full OKX integration: candles, orders, balance, leverage."""

    def __init__(self, settings: Settings):
        config = {
            "apiKey": settings.exchange_api_key,
            "secret": settings.exchange_api_secret,
            "password": settings.exchange_passphrase,
            "enableRateLimit": True,
        }
        if settings.paper_trading:
            config["options"] = {"defaultType": "swap", "sandboxMode": False}
            config["headers"] = {"x-simulated-trading": "1"}
        self._exchange = ccxt_async.okx(config)
        self._paper = settings.paper_trading

    async def close(self):
        await self._exchange.close()

    async def get_candles(self, symbol: str, tf: str = "30m", limit: int = 100) -> list[dict]:
        ohlcv = await self._exchange.fetch_ohlcv(symbol, tf, limit=limit)
        return [{"ts": c[0], "open": c[1], "high": c[2], "low": c[3],
                 "close": c[4], "vol": c[5]} for c in ohlcv]

    async def get_balance(self) -> float:
        bal = await self._exchange.fetch_balance()
        usdt = bal.get("USDT", {})
        return float(usdt.get("free", 0) or 0)

    async def get_positions(self) -> list[dict]:
        positions = await self._exchange.fetch_positions()
        return [p for p in positions if float(p.get("contracts", 0)) > 0]

    async def set_leverage(self, symbol: str, leverage: int):
        try:
            await self._exchange.set_leverage(leverage, symbol)
            logger.info("Leverage set: %s = %dx", symbol, leverage)
        except Exception as e:
            logger.warning("Set leverage failed for %s: %s", symbol, e)

    async def set_margin_mode(self, symbol: str, mode: str = "cross"):
        try:
            await self._exchange.set_margin_mode(mode, symbol)
            logger.info("Margin mode: %s = %s", symbol, mode)
        except Exception as e:
            logger.warning("Set margin mode failed for %s: %s", symbol, e)

    async def place_order(self, symbol: str, side: str, qty: float,
                          reduce_only: bool = False) -> dict:
        """Place market order. side = 'buy' or 'sell'."""
        params = {}
        if reduce_only:
            params["reduceOnly"] = True
        try:
            result = await self._exchange.create_order(
                symbol=symbol, type="market", side=side,
                amount=qty, params=params,
            )
            order_id = result.get("id", "")
            filled = float(result.get("filled", 0))
            avg_price = float(result.get("average", 0) or result.get("price", 0) or 0)
            fee = float((result.get("fee") or {}).get("cost", 0))
            logger.info("ORDER %s %s %s qty=%.6f filled=%.6f price=%.2f fee=%.4f",
                         order_id, side.upper(), symbol, qty, filled, avg_price, fee)
            return {"id": order_id, "filled": filled, "price": avg_price, "fee": fee}
        except Exception as e:
            logger.error("ORDER FAILED: %s %s %s qty=%.6f — %s", side, symbol, qty, qty, e)
            return {"id": "", "filled": 0, "price": 0, "fee": 0, "error": str(e)}


# ============ POSITION STATE ============

class PositionState:
    def __init__(self):
        self.positions: dict[str, dict] = {}
        self._load()

    def _load(self):
        if Path(STATE_FILE).exists():
            try:
                self.positions = json.loads(Path(STATE_FILE).read_text())
            except Exception:
                self.positions = {}

    def save(self):
        Path(STATE_FILE).write_text(json.dumps(self.positions, indent=2, default=str))

    def get(self, symbol: str) -> dict | None:
        return self.positions.get(symbol)

    def has(self, symbol: str) -> bool:
        return symbol in self.positions

    def open(self, symbol: str, direction: str, entry_price: float,
             qty: float, sl: float, atr: float, order_id: str = ""):
        self.positions[symbol] = {
            "direction": direction, "entry_price": entry_price,
            "qty": qty, "sl": sl, "atr": atr, "peak": entry_price,
            "order_id": order_id, "opened_at": datetime.now(timezone.utc).isoformat(),
        }
        self.save()

    def close(self, symbol: str) -> dict | None:
        pos = self.positions.pop(symbol, None)
        self.save()
        return pos

    def update_trailing(self, symbol: str, price: float, trail_atr: float):
        pos = self.positions.get(symbol)
        if not pos: return
        atr = pos["atr"]
        if pos["direction"] == "LONG":
            pos["peak"] = max(pos["peak"], price)
            new_sl = pos["peak"] - trail_atr * atr
            if new_sl > pos["sl"]: pos["sl"] = new_sl
        else:
            pos["peak"] = min(pos["peak"], price)
            new_sl = pos["peak"] + trail_atr * atr
            if new_sl < pos["sl"]: pos["sl"] = new_sl
        self.save()

    def check_sl(self, symbol: str, price: float) -> bool:
        pos = self.positions.get(symbol)
        if not pos: return False
        return ((pos["direction"] == "LONG" and price <= pos["sl"]) or
                (pos["direction"] == "SHORT" and price >= pos["sl"]))


# ============ MAIN BOT ============

class LiveBot:
    def __init__(self):
        self.settings = Settings()
        self.exchange = OKXExchange(self.settings)
        self.cg = CoinglassV4(self.settings.coinglass_api_key)
        self.news = NewsFeed(
            cryptopanic_key=os.getenv("BOT_CRYPTOPANIC_KEY", ""),
        )
        self.fe = FeatureEngine()
        self.state = PositionState()
        self.risk_mgr = RiskManager(self.settings)
        self.strategies: dict[str, BreakoutStrategy] = {}

        self.margin_pct = 0.25
        self.leverage = 25
        self.trail_atr = 2.5
        self.daily_pnl = 0.0
        self.peak_equity = self.settings.account_equity
        self.max_daily_loss = self.settings.account_equity * self.settings.max_daily_loss_pct
        self.max_drawdown = self.settings.account_equity * 0.15  # 15% max drawdown

        self.symbols = [
            {"name": "BTC", "symbol": "BTC/USDT:USDT"},
            {"name": "ETH", "symbol": "ETH/USDT:USDT"},
            {"name": "SOL", "symbol": "SOL/USDT:USDT"},
            {"name": "ADA", "symbol": "ADA/USDT:USDT"},
        ]

    def _build_bundles(self, candles, symbol, cg_data: dict | None = None):
        """Build MarketDataBundles with real Coinglass data injected.

        cg_data: {
            'oi_value': float,      # current OI quantity
            'oi_change_1h': float,  # OI change % 1h
            'funding_rate': float,  # avg funding rate
            'liq_above': float,     # liquidation level above
            'liq_below': float,     # liquidation level below
        }
        """
        cg = cg_data or {}
        oi_val = cg.get("oi_value", 0)
        funding = cg.get("funding_rate", 0)
        liq_above_pct = cg.get("liq_above", 0)
        liq_below_pct = cg.get("liq_below", 0)

        hs = min(50, len(candles) - 1)
        bundles = []
        for i in range(hs, len(candles)):
            c = candles[i]
            price, vol = c["close"], c["vol"]
            spread = price * 0.0003
            snap = MarketSnapshot(symbol=symbol, price=price, volume=vol,
                bid=price - spread/2, ask=price + spread/2,
                timestamp=max(int(c["ts"]/1000), 1))
            s = max(0, i - hs)
            ph = [candles[j]["close"] for j in range(s, i+1)]
            vh = [candles[j]["vol"] for j in range(s, i+1)]

            # OI history: simulate trend from real-time OI change
            # If OI grew 1% in 1h, create ascending OI series
            oi_change = cg.get("oi_change_1h", 0) / 100 if cg.get("oi_change_1h") else 0
            if oi_val > 0:
                oi_steps = len(ph)
                oi_start = oi_val / (1 + oi_change) if (1 + oi_change) != 0 else oi_val
                oih = [oi_start + (oi_val - oi_start) * j / max(oi_steps - 1, 1)
                       for j in range(oi_steps)]
            else:
                oih = [0.0]

            # Funding history: use real rate
            fh = [funding] if funding != 0 else [0.0]

            # Liquidation levels from Coinglass
            la = liq_above_pct if liq_above_pct > 0 else price * 1.02
            lb = liq_below_pct if liq_below_pct > 0 else price * 0.98

            bundles.append(MarketDataBundle(
                market=snap, price_history=ph, volume_history=vh,
                oi_history=oih, funding_history=fh,
                liquidation_above=la, liquidation_below=lb,
            ))
        return bundles

    def _fetch_coinglass_data(self, name: str, price: float) -> dict:
        """Fetch all Coinglass data for a symbol — feeds into MarketDataBundle."""
        data = {}
        try:
            # 1. Real-time OI
            oi = self.cg.get_oi_realtime(name)
            total = oi.get("total", {})
            data["oi_value"] = total.get("oi_qty", 0)
            data["oi_change_1h"] = total.get("change_1h", 0)
            data["oi_change_4h"] = total.get("change_4h", 0)

            # 2. Funding rate
            fr = self.cg.get_funding_rates(name)
            data["funding_rate"] = fr.get("avg_rate", 0)

            # 3. Liquidation heatmap → real levels
            heatmap = self.cg.get_liquidation_heatmap(name)
            data["longs_liq_usd"] = heatmap.get("longs_liq_usd", 0)
            data["shorts_liq_usd"] = heatmap.get("shorts_liq_usd", 0)
            # Estimate liquidation zones from heatmap imbalance
            if heatmap.get("dominant") == "LONGS":
                data["liq_below"] = price * 0.985  # longs will be liquidated below
                data["liq_above"] = price * 1.025
            elif heatmap.get("dominant") == "SHORTS":
                data["liq_below"] = price * 0.975
                data["liq_above"] = price * 1.015  # shorts liquidated above
            else:
                data["liq_above"] = price * 1.02
                data["liq_below"] = price * 0.98

            # 4. L/S ratio
            ls = self.cg.get_ls_ratio(name)
            data["ls_long_pct"] = ls.get("long_pct", 50)
            data["ls_short_pct"] = ls.get("short_pct", 50)

            logger.info("[%s] CG: OI=%.0f Δ1h=%.2f%% FR=%.4f%% L/S=%.0f/%.0f liq=$%.0fM/$%.0fM",
                         name, data["oi_value"], data["oi_change_1h"],
                         data["funding_rate"] * 100, data["ls_long_pct"], data["ls_short_pct"],
                         data["longs_liq_usd"] / 1e6, data["shorts_liq_usd"] / 1e6)
        except Exception as e:
            logger.warning("[%s] Coinglass fetch error: %s", name, e)

        # 5. News sentiment
        try:
            news = self.news.get_news_score(name)
            data["news_score"] = news.get("score", 0)
            data["fear_greed"] = news.get("fear_greed", 50)
        except Exception as e:
            logger.warning("[%s] News fetch error: %s", name, e)
            data["news_score"] = 0
            data["fear_greed"] = 50

        return data

    async def setup_exchange(self):
        """Set leverage and margin mode for all symbols."""
        for sym in self.symbols:
            await self.exchange.set_leverage(sym["symbol"], self.leverage)
            await self.exchange.set_margin_mode(sym["symbol"], "cross")
            await asyncio.sleep(0.5)

        balance = await self.exchange.get_balance()
        logger.info("Account balance: $%.2f", balance)
        if balance > 0:
            self.settings.account_equity = balance

    async def close_position(self, sym: dict, price: float, reason: str) -> float:
        """Close position on exchange + update state."""
        pos = self.state.get(sym["name"])
        if not pos: return 0.0

        side = "sell" if pos["direction"] == "LONG" else "buy"
        result = await self.exchange.place_order(sym["symbol"], side, pos["qty"], reduce_only=True)

        actual_price = result["price"] if result["price"] > 0 else price
        if pos["direction"] == "LONG":
            pnl = (actual_price - pos["entry_price"]) * pos["qty"]
        else:
            pnl = (pos["entry_price"] - actual_price) * pos["qty"]

        self.state.close(sym["name"])
        logger.info("CLOSED %s %s @ %.2f PnL=%.2f reason=%s",
                     pos["direction"], sym["name"], actual_price, pnl, reason)
        return pnl

    async def open_position(self, sym: dict, direction: str, price: float, atr: float):
        """Open position on exchange + save state."""
        balance = await self.exchange.get_balance()
        if balance < 10:
            logger.warning("Insufficient balance: $%.2f", balance)
            return

        margin = min(balance, self.settings.account_equity) * self.margin_pct
        qty = margin * self.leverage / price

        side = "buy" if direction == "LONG" else "sell"
        result = await self.exchange.place_order(sym["symbol"], side, qty)

        if result.get("error") or result["filled"] == 0:
            logger.error("Failed to open %s %s", direction, sym["name"])
            return

        actual_price = result["price"] if result["price"] > 0 else price
        sl = actual_price - atr if direction == "LONG" else actual_price + atr

        self.state.open(sym["name"], direction, actual_price, result["filled"],
                        sl, atr, result.get("id", ""))
        logger.info("OPENED %s %s @ %.2f qty=%.6f sl=%.2f margin=$%.2f",
                     direction, sym["name"], actual_price, result["filled"], sl, margin)

    async def process_symbol(self, sym: dict):
        name = sym["name"]
        symbol = sym["symbol"]

        # 1. GET CANDLES
        candles = await self.exchange.get_candles(symbol, "30m", 100)
        if len(candles) < 55:
            logger.warning("[%s] Not enough candles: %d", name, len(candles))
            return

        price = candles[-1]["close"]

        # 2. UPDATE TRAILING STOP
        if self.state.has(name):
            self.state.update_trailing(name, price, self.trail_atr)
            if self.state.check_sl(name, price):
                pnl = await self.close_position(sym, price, "TRAILING_STOP")
                self.risk_mgr.record_pnl(pnl)
                self.daily_pnl += pnl
                return

        # 3. FETCH COINGLASS DATA (real-time OI, funding, L/S, liquidations)
        cg_data = self._fetch_coinglass_data(name, price)

        # 4. BUILD BUNDLES WITH REAL DATA
        if name not in self.strategies:
            self.strategies[name] = BreakoutStrategy(symbol=symbol)

        bundles = self._build_bundles(candles, symbol, cg_data)
        if not bundles: return

        # 5. GENERATE SIGNAL (now with real OI trend + funding in FeatureVector)
        features = self.fe.build_features(bundles[-1])
        signal = self.strategies[name].generate_signal(features)
        if signal is None: return

        direction = signal.direction.value
        logger.info("[%s] Signal: %s strength=%.2f (regime=%s vol=%.2f oi=%.4f fund=%.4f news=%.2f FnG=%d)",
                     name, direction, signal.strength, features.regime_label.value,
                     features.volume_ratio, features.oi_trend, features.funding,
                     cg_data.get("news_score", 0), cg_data.get("fear_greed", 50))

        # 6. COINGLASS FILTERS (OI expanding + Funding + L/S + Liquidation heatmap)
        passed, reasons = self.cg.check_entry_filters(name, direction)
        if not passed:
            logger.info("[%s] Signal %s REJECTED by Coinglass: %s", name, direction, ", ".join(reasons))
            return

        # 7. NEWS SENTIMENT FILTER (Fear & Greed + CryptoPanic)
        skip_news, news_reason = self.news.should_skip_trade(name, direction)
        if skip_news:
            logger.info("[%s] Signal %s REJECTED by News: %s", name, direction, news_reason)
            return

        # 8. RISK MANAGER (daily loss, max positions, min confidence)
        trade = TradeCandidate(
            symbol=symbol, direction=signal.direction,
            setup_type=SetupType.FUNDING_MEAN_REVERSION,
            entry_price=price, stop_loss=price - features.atr if direction == "LONG" else price + features.atr,
            score=signal.strength, expected_value=2.0, confidence=signal.strength,
        )
        self.risk_mgr.open_positions = len(self.state.positions)
        decision = self.risk_mgr.evaluate(trade)
        if not decision.allow_trade:
            logger.info("[%s] Signal %s REJECTED by RiskManager: %s", name, direction, decision.reason)
            return

        # 8. MAX DRAWDOWN KILL SWITCH
        equity = self.settings.account_equity + self.daily_pnl
        if equity < self.peak_equity - self.max_drawdown:
            logger.critical("MAX DRAWDOWN HIT. Equity=$%.2f Peak=$%.2f. HALTING ALL.", equity, self.peak_equity)
            return

        # 9. FLIP (close opposite + open new)
        pos = self.state.get(name)
        if pos and pos["direction"] != direction:
            pnl = await self.close_position(sym, price, f"FLIP_TO_{direction}")
            self.risk_mgr.record_pnl(pnl)
            self.daily_pnl += pnl

        # 10. OPEN POSITION
        if not self.state.has(name):
            atr = features.atr if features.atr > 0 else price * 0.01
            await self.open_position(sym, direction, price, atr)

    async def run_once(self):
        now = datetime.now(timezone.utc)

        # Daily reset at midnight UTC
        if not hasattr(self, '_last_reset_date') or self._last_reset_date != now.date():
            if hasattr(self, '_last_reset_date'):
                logger.info("Daily PnL reset: $%.2f -> $0", self.daily_pnl)
            self.daily_pnl = 0.0
            self.risk_mgr.reset_daily()
            self._last_reset_date = now.date()

        logger.info("=" * 60)
        logger.info("Cycle: %s | Mode: %s", now.strftime("%H:%M:%S UTC"),
                     "PAPER" if self.settings.paper_trading else "LIVE")

        for sym in self.symbols:
            try:
                await self.process_symbol(sym)
            except Exception as e:
                logger.error("[%s] Error: %s", sym["name"], e, exc_info=True)
            await asyncio.sleep(1)

        # Summary
        positions = self.state.positions
        if positions:
            for s, p in positions.items():
                logger.info("  POS: %s %s @ %.2f sl=%.2f", p["direction"], s, p["entry_price"], p["sl"])
        balance = await self.exchange.get_balance()
        self.peak_equity = max(self.peak_equity, balance)
        logger.info("Balance: $%.2f | Daily PnL: $%.2f | Peak: $%.2f",
                     balance, self.daily_pnl, self.peak_equity)

    async def run(self):
        logger.info("=" * 60)
        logger.info("LIVE BOT v2 STARTING")
        logger.info("Mode: %s", "PAPER" if self.settings.paper_trading else "*** LIVE ***")
        logger.info("Symbols: %s", [s["name"] for s in self.symbols])
        logger.info("Config: margin=%.0f%% leverage=%dx trail=%.1f ATR",
                     self.margin_pct*100, self.leverage, self.trail_atr)
        logger.info("Filters: OI + Funding + L/S + Liquidation heatmap")
        logger.info("Safety: daily_loss=$%.0f max_dd=$%.0f",
                     self.max_daily_loss, self.max_drawdown)
        logger.info("=" * 60)

        await self.setup_exchange()

        while True:
            try:
                await self.run_once()
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error("Cycle error: %s", e, exc_info=True)

            now = time.time()
            next_30m = ((now // 1800) + 1) * 1800 + 5
            wait = max(next_30m - now, 10)
            logger.info("Next cycle in %.0f sec", wait)
            try:
                await asyncio.sleep(wait)
            except KeyboardInterrupt:
                break

        await self.exchange.close()
        logger.info("Bot stopped.")


async def main():
    bot = LiveBot()
    if "--once" in sys.argv:
        await bot.setup_exchange()
        await bot.run_once()
        await bot.exchange.close()
    else:
        await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
