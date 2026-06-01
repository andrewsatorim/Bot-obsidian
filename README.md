# Bot Obsidian

Multi-Layer Crypto Decision Engine — a modular algorithmic trading system for crypto
derivatives, built on a hexagonal (ports & adapters) architecture.

All domain logic sits behind abstract port interfaces (`app/ports/`); concrete adapters
(exchange feeds, executors, storage, Telegram) are injected at runtime. This keeps the
decision pipeline testable and venue-agnostic.

## What's implemented

This is a working system, not a skeleton. It includes:

- **Decision pipeline** (`app/core/orchestrator.py`) — a state machine that wires
  `data feed → feature engine → strategy → risk → execution`, with a dedicated
  `ExitManager` for stop/trail/partial-exit logic. `MultiOrchestrator` runs several
  symbols in parallel with a portfolio-level correlation guard.
- **15 strategies** (`app/strategy/`) — each implements `StrategyPort.generate_signal()`.
- **Market data feeds** (`app/feeds/`) — CCXT, Coinglass (v1 + v4), historical, news,
  and a simulated feed for paper trading.
- **Execution adapters** (`app/execution/`) — live CCXT executor and a paper executor.
- **Risk management** (`app/risk/risk_manager.py`) — position sizing, daily-loss limits,
  max open positions, confidence gating.
- **Backtesting** (`app/backtest/engine.py`) — multi-TP-level backtest engine, plus many
  ad-hoc research scripts under `scripts/`.
- **Monitoring** (`app/monitoring/`) — health endpoint (port 8080) and metrics.
- **Storage** (`app/storage/sqlite_storage.py`) — SQLite-backed state persistence.
- **Telegram bot** (`app/telegram/bot_adapter.py`) — trade notifications and control.
- **Dashboard** (`app/api/` + `webapp/`) — a Telegram Mini App: FastAPI REST + WebSocket
  backend serving a static front-end with several design variants.
- **Tests** (`tests/`) — pytest unit and contract tests across models, orchestrator,
  strategies, risk, backtest, exit manager, and monitoring.

## Architecture

```
app/
  core/         # Orchestrator, MultiOrchestrator, ExitManager — pipeline wiring
  state/        # EngineState state machine (IDLE→SCANNING→…→POSITION_OPEN→COOLDOWN)
  analytics/    # FeatureEngine (AnalyticsPort) — builds FeatureVector from market data
  strategy/     # 15 StrategyPort implementations + fusion / super strategy
  risk/         # RiskManager (RiskPort) — sizing & portfolio risk controls
  execution/    # CCXT (live) and paper executors (ExecutionPort)
  feeds/        # CCXT / Coinglass / historical / news / simulated (DataFeedPort)
  models/       # Pydantic DTOs (pure data, no business logic)
  ports/        # Abstract interfaces (ABCs) — the contracts
  monitoring/   # health + metrics
  storage/      # SQLite persistence (StoragePort)
  telegram/     # Telegram bot adapter (TelegramControlPort)
  api/          # FastAPI dashboard backend (REST + WebSocket)
webapp/         # Telegram Mini App front-end (HTML/CSS/JS + design variants)
scripts/        # backtests, optimizers, and live-run helpers
tests/          # pytest suite
```

### Strategies

`aura_v14`, `bollinger_reversion`, `breakout`, `breakout_nooi`, `candle_volume`,
`donchian`, `elliott`, `funding_mean_reversion`, `liquidation_squeeze`, `oi_divergence`,
`reversal`, `swing`, `trend_following`, plus the composites `super_strategy` and
`fusion` (`StrategyFusion`, a weighted blend with agreement/strength thresholds).

`app/main.py` runs a `StrategyFusion` of six strategies by default.

## Setup

Requires Python 3.11+.

```bash
pip install -e ".[dev]"
```

Copy `.env.example` to `.env` and fill in the `BOT_`-prefixed settings (exchange keys,
Telegram token, etc.). All config lives in `app/config.py` (`Settings`). The default is
**paper trading** (`BOT_PAPER_TRADING=true`), which uses the simulated feed and paper
executor — no real orders.

## Running

```bash
# Trading engine (paper by default)
bot-obsidian            # or: python -m app.main

# Dashboard (Telegram Mini App backend) on http://localhost:8080
bot-dashboard           # or: python -m app.api.run --port 8080
```

Backtests and research live in `scripts/` (e.g. `python scripts/test_all_strategies.py`).

## Tests

```bash
pytest
```

## Branches

This `develop` branch consolidates the full system. Historical context:

- `main` — the original architecture skeleton (kept for history).
- `claude/code-review-rating-Z8Ett` — the full trading engine, the base of `develop`.
- `claude/crypto-bot-dashboard-wyH6k` — origin of the dashboard (`app/api/` + `webapp/`).
- `fix/agents-improvements` — origin of `AGENTS.md` and `docs/`.
