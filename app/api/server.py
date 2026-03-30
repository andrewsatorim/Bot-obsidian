"""FastAPI server for Telegram Mini App dashboard.

Serves REST API + WebSocket for real-time updates.
Static files for the Mini App are served from /webapp.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logger = logging.getLogger(__name__)

POSITIONS_FILE = Path("data/positions.json")
WEBAPP_DIR = Path(__file__).resolve().parent.parent.parent / "webapp"


# ---- Response models ----

class PositionResponse(BaseModel):
    symbol: str
    direction: str
    entry_price: float
    qty: float
    sl: float
    atr: float
    peak: float
    order_id: str = ""
    opened_at: str = ""
    unrealized_pnl: float = 0.0
    pnl_pct: float = 0.0


class PnLResponse(BaseModel):
    daily_pnl: float
    total_equity: float
    peak_equity: float
    drawdown_pct: float
    positions_count: int


class MarketDataResponse(BaseModel):
    symbol: str
    price: float
    volume: float
    change_24h: float
    oi_change_1h: float
    funding_rate: float
    fear_greed: int
    regime: str


class SignalResponse(BaseModel):
    symbol: str
    direction: str
    strength: float
    timestamp: int
    filters_passed: list[str]
    filters_rejected: list[str]


class AlertResponse(BaseModel):
    id: int
    timestamp: float
    level: str
    symbol: str
    message: str


class BotSettingsResponse(BaseModel):
    symbols: list[str]
    margin_pct: float
    leverage: int
    trail_atr: float
    max_daily_loss_pct: float
    max_drawdown_pct: float
    max_open_positions: int
    min_confidence: float
    scan_interval_sec: float
    paper_trading: bool


class BotStatusResponse(BaseModel):
    running: bool
    mode: str
    uptime_seconds: float
    last_cycle: str
    symbols: list[str]
    positions: list[PositionResponse]
    pnl: PnLResponse
    settings: BotSettingsResponse


# ---- State store (shared with bot process) ----

class DashboardState:
    """In-memory state synced from the live bot. Thread-safe reads."""

    def __init__(self) -> None:
        self.positions: dict[str, dict] = {}
        self.daily_pnl: float = 0.0
        self.equity: float = 10_000.0
        self.peak_equity: float = 10_000.0
        self.signals: list[dict] = []
        self.alerts: list[dict] = []
        self.market_data: dict[str, dict] = {}
        self.settings: dict[str, Any] = {
            "symbols": ["BTC", "ETH", "SOL", "ADA"],
            "margin_pct": 0.25,
            "leverage": 25,
            "trail_atr": 2.5,
            "max_daily_loss_pct": 0.05,
            "max_drawdown_pct": 0.15,
            "max_open_positions": 4,
            "min_confidence": 0.3,
            "scan_interval_sec": 1800.0,
            "paper_trading": True,
        }
        self.running: bool = False
        self.start_time: float = time.time()
        self.last_cycle: str = ""
        self._alert_counter: int = 0

    def load_positions(self) -> None:
        if POSITIONS_FILE.exists():
            try:
                self.positions = json.loads(POSITIONS_FILE.read_text())
            except Exception:
                self.positions = {}

    def add_alert(self, level: str, symbol: str, message: str) -> None:
        self._alert_counter += 1
        self.alerts.append({
            "id": self._alert_counter,
            "timestamp": time.time(),
            "level": level,
            "symbol": symbol,
            "message": message,
        })
        if len(self.alerts) > 200:
            self.alerts = self.alerts[-200:]

    def add_signal(self, signal: dict) -> None:
        self.signals.append(signal)
        if len(self.signals) > 100:
            self.signals = self.signals[-100:]

    def update_market(self, symbol: str, data: dict) -> None:
        self.market_data[symbol] = {**data, "updated_at": time.time()}


state = DashboardState()


# ---- WebSocket manager ----

class ConnectionManager:
    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.remove(ws)

    async def broadcast(self, data: dict) -> None:
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.remove(ws)

    @property
    def count(self) -> int:
        return len(self._connections)


ws_manager = ConnectionManager()


# ---- FastAPI app ----

app = FastAPI(title="Bot-Obsidian Dashboard", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Static files (Mini App) ----

@app.on_event("startup")
async def startup() -> None:
    state.load_positions()
    state.running = True
    asyncio.create_task(_broadcast_loop())


async def _broadcast_loop() -> None:
    """Push state to all WebSocket clients every 2 seconds."""
    while True:
        if ws_manager.count > 0:
            state.load_positions()
            await ws_manager.broadcast(_build_snapshot())
        await asyncio.sleep(2)


def _build_snapshot() -> dict:
    positions = []
    for sym, p in state.positions.items():
        entry = p.get("entry_price", 0)
        market = state.market_data.get(sym, {})
        current_price = market.get("price", entry)
        qty = p.get("qty", 0)
        direction = p.get("direction", "LONG")
        if direction == "LONG":
            pnl = (current_price - entry) * qty
        else:
            pnl = (entry - current_price) * qty
        pnl_pct = (pnl / (entry * qty) * 100) if entry * qty > 0 else 0
        positions.append({
            "symbol": sym,
            "direction": direction,
            "entry_price": entry,
            "qty": qty,
            "sl": p.get("sl", 0),
            "atr": p.get("atr", 0),
            "peak": p.get("peak", entry),
            "order_id": p.get("order_id", ""),
            "opened_at": p.get("opened_at", ""),
            "unrealized_pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
        })

    drawdown = 0.0
    if state.peak_equity > 0:
        drawdown = (state.peak_equity - state.equity - state.daily_pnl) / state.peak_equity * 100

    return {
        "type": "snapshot",
        "ts": time.time(),
        "positions": positions,
        "pnl": {
            "daily_pnl": round(state.daily_pnl, 2),
            "total_equity": round(state.equity, 2),
            "peak_equity": round(state.peak_equity, 2),
            "drawdown_pct": round(max(drawdown, 0), 2),
            "positions_count": len(positions),
        },
        "market": state.market_data,
        "signals": state.signals[-10:],
        "alerts": state.alerts[-20:],
        "settings": state.settings,
        "status": {
            "running": state.running,
            "mode": "PAPER" if state.settings.get("paper_trading") else "LIVE",
            "uptime_seconds": round(time.time() - state.start_time),
            "last_cycle": state.last_cycle,
            "ws_clients": ws_manager.count,
        },
    }


# ---- REST endpoints ----

@app.get("/api/status")
async def get_status() -> dict:
    state.load_positions()
    return _build_snapshot()


@app.get("/api/positions")
async def get_positions() -> list[dict]:
    state.load_positions()
    return _build_snapshot()["positions"]


@app.get("/api/pnl")
async def get_pnl() -> dict:
    return _build_snapshot()["pnl"]


@app.get("/api/market/{symbol}")
async def get_market(symbol: str) -> dict:
    data = state.market_data.get(symbol.upper(), {})
    if not data:
        return {"symbol": symbol.upper(), "price": 0, "error": "no data"}
    return data


@app.get("/api/signals")
async def get_signals(limit: int = 20) -> list[dict]:
    return state.signals[-limit:]


@app.get("/api/alerts")
async def get_alerts(limit: int = 50) -> list[dict]:
    return state.alerts[-limit:]


@app.get("/api/settings")
async def get_settings() -> dict:
    return state.settings


@app.post("/api/settings")
async def update_settings(updates: dict) -> dict:
    allowed = {
        "margin_pct", "leverage", "trail_atr", "max_daily_loss_pct",
        "max_open_positions", "min_confidence", "paper_trading",
    }
    applied = {}
    for key, val in updates.items():
        if key in allowed:
            state.settings[key] = val
            applied[key] = val
    if applied:
        state.add_alert("INFO", "SYSTEM", f"Settings updated: {applied}")
    return {"updated": applied}


# ---- WebSocket ----

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws_manager.connect(ws)
    try:
        # Send initial snapshot
        await ws.send_json(_build_snapshot())
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await ws.send_json({"type": "pong", "ts": time.time()})
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
    except Exception:
        ws_manager.disconnect(ws)


# ---- Serve Mini App ----

@app.get("/")
async def serve_index() -> FileResponse:
    return FileResponse(WEBAPP_DIR / "index.html")


if WEBAPP_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEBAPP_DIR)), name="static")
