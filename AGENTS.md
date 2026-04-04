# AGENTS.md — Bot Obsidian

Agent instructions for working in this repository.

---

## Project

**Bot Obsidian** is a multi-layer crypto decision engine written in Python 3.11+.
It uses a hexagonal (ports-and-adapters) architecture. All domain logic is isolated
behind abstract port interfaces; concrete adapters are injected at runtime.

```
app/
  analytics/      # FeatureEngine (AnalyticsPort impl)
  core/           # Orchestrator — wires the pipeline
  models/         # Pydantic DTOs (no business logic)
  ports/          # Abstract interfaces (ABCs)
  state/          # StateMachine for engine lifecycle
tests/            # pytest unit + contract tests (to be created)
```

---

## Language and runtime

- Python 3.11+
- Pydantic v2 for all DTOs
- `pyproject.toml` is the single source of truth for metadata and tool config
- No `requirements.txt` — use `pyproject.toml` `[project.dependencies]`

---

## Code conventions

- Line length: 100 (enforced by Black)
- Type annotations required on all public functions and methods
- `from __future__ import annotations` at the top of every module
- ABCs live in `app/ports/`; concrete implementations live in their domain folder
- Models are pure data — no methods, no business logic
- Async I/O for all external calls (feeds, exchange, Telegram)
- Every package directory must have an `__init__.py`

---

## Adding a new module

1. Define the port interface in `app/ports/<name>_port.py` (ABC).
2. Implement the adapter in the appropriate domain folder.
3. Wire it into `Orchestrator.__init__` via constructor injection.
4. Add the dependency to `pyproject.toml` if a third-party library is needed.
5. Write a contract test in `tests/` that exercises the port interface.

---

## Testing

```bash
pytest                  # run all tests
pytest -x               # stop on first failure
pytest --tb=short       # compact tracebacks
```

- Tests live in `tests/` mirroring the `app/` structure.
- Use `pytest` fixtures for dependency injection; never patch global state.
- Contract tests must cover every abstract port method.
- Unit tests for `FeatureEngine` must cover each `_compute_*` helper independently.

---

## Commit style

```
<scope>: <imperative summary>

Optional body explaining motivation.
```

Examples:
- `feat(analytics): add RSI feature to FeatureVector`
- `fix(orchestrator): prevent double-execution on VALIDATING re-entry`
- `test(feature_engine): add ATR proxy edge cases`

---

## What is NOT implemented yet

The following modules are stubs — do not assume they work:

- `app/strategy/` — no setup detection or signal fusion
- `app/risk/` — no sizing or portfolio controls
- `app/execution/` — no order routing or position management
- `app/feeds/` — no exchange, derivatives, news, on-chain, or social adapters
- `app/telegram/` — no bot or mini app adapter

Implement in this order: feeds → strategy → risk → execution → telegram.

---

## Environment

- Dev container: `mcr.microsoft.com/devcontainers/universal:4.0.1-noble`
- No secrets are committed; use environment variables for API keys
- Required env vars (document here as they are added):
  - `TELEGRAM_BOT_TOKEN`
  - `EXCHANGE_API_KEY` / `EXCHANGE_API_SECRET`
