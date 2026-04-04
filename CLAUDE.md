# CLAUDE.md — Bot Obsidian

## Project Overview

Bot Obsidian is a **Multi-Layer Crypto Decision Engine** — a modular cryptocurrency trading system built with a hexagonal (ports-and-adapters) architecture in Python 3.11+.

## Architecture

```
app/
├── models/      # Domain DTOs (Pydantic-style dataclasses)
├── ports/       # Abstract service interfaces (ABCs)
├── core/        # Orchestrator — wires data → features → strategy → risk → execution
├── analytics/   # Feature engineering (FeatureEngine)
├── state/       # StateMachine with 8-state deterministic lifecycle
├── strategy/    # Setup detection and signal generation (planned)
├── risk/        # Sizing and portfolio risk controls (planned)
├── execution/   # Venue selection, order routing (planned)
├── feeds/       # Exchange, derivatives, news, on-chain inputs (planned)
└── telegram/    # Bot and Mini App control surface (planned)
tests/           # Unit and contract tests
```

### Key patterns

- **Hexagonal / Ports & Adapters**: all external I/O is behind abstract ports in `app/ports/`
- **State Machine**: `app/state/state_machine.py` — IDLE → SCANNING → SETUP_FOUND → VALIDATING → EXECUTING → POSITION_OPEN, with COOLDOWN and HALTED states
- **Orchestrator**: `app/core/orchestrator.py` — async pipeline driven by the state machine
- **Models are DTOs**: thin data containers, no business logic

## Code Style & Conventions

- **Formatter**: `black` with `line-length = 100`
- **Python**: 3.11+ (use modern syntax: `X | Y` unions, `match/case` when appropriate)
- **Imports**: use `from __future__ import annotations` in every module
- **No `__init__.py`**: project uses implicit namespace packages
- **Type hints**: all function signatures must be fully typed
- **Async**: data feeds and execution are async (`async def` / `await`)
- **Naming**: snake_case for functions/variables, PascalCase for classes, UPPER_SNAKE for constants

## Testing

- Framework: `pytest`
- Test directory: `tests/`
- Run tests: `python -m pytest`
- When implementing new functionality, write tests alongside the code

## Development Rules

1. **Respect the ports-and-adapters boundary** — never import concrete implementations in core/strategy/risk logic; depend on ports only.
2. **Keep models thin** — DTOs carry data, not behavior.
3. **One responsibility per module** — if a file grows beyond ~200 lines, consider splitting.
4. **All state transitions go through StateMachine** — never mutate engine state directly.
5. **No secrets in code** — API keys, exchange credentials, and tokens go in environment variables or `.env` (never committed).
6. **Async-first for I/O** — any port that touches network must use async.

## Implementation Priority

1. Data contracts and interfaces
2. Feature engine
3. Strategy engine
4. Risk and execution
5. Telegram control plane
