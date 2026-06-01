# AGENTS-IMPROVEMENT-SPEC.md

Concrete improvements required before this codebase is agent-workable and production-safe.
Items are ordered by impact. Each item states the problem, the fix, and the acceptance criterion.

---

## 1. Missing `__init__.py` files — packages are not importable

**Problem:** Every directory under `app/` lacks `__init__.py`. Python cannot resolve
`from app.models.signal import Signal` without them. Any agent that tries to run or test
the code will get `ModuleNotFoundError`.

**Fix:** Create empty `__init__.py` in:
```
app/
app/analytics/
app/core/
app/models/
app/ports/
app/state/
tests/
```

**Acceptance:** `python -c "from app.core.orchestrator import Orchestrator"` exits 0.

---

## 2. No dependencies declared in `pyproject.toml`

**Problem:** `pyproject.toml` has no `[project.dependencies]`. The code imports `pydantic`
but nothing pins it. An agent running `pip install -e .` gets a bare environment and
`ImportError: No module named 'pydantic'`.

**Fix:** Add to `pyproject.toml`:
```toml
[project.dependencies]
pydantic = ">=2.0,<3"

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23", "black>=24"]
```

**Acceptance:** `pip install -e .[dev]` succeeds; `python -c "import pydantic"` exits 0.

---

## 3. No tests exist

**Problem:** `pyproject.toml` declares `testpaths = ["tests"]` but the `tests/` directory
does not exist. There is no way to verify correctness or catch regressions.

**Fix:** Create the following test files as a baseline:

- `tests/__init__.py`
- `tests/test_state_machine.py` — all valid and invalid transitions
- `tests/test_feature_engine.py` — each `_compute_*` helper, edge cases (empty lists,
  zero division, single-element sequences), and `build_features` with both a bare
  `MarketSnapshot` and a full dict bundle
- `tests/test_orchestrator.py` — mock all ports; verify state transitions through a full
  IDLE → SCANNING → SETUP_FOUND → VALIDATING → EXECUTING → POSITION_OPEN cycle

**Acceptance:** `pytest` collects ≥ 20 tests and all pass.

---

## 4. `Orchestrator.step()` re-fetches and re-computes on every state

**Problem:** `SCANNING`, `VALIDATING`, and `EXECUTING` each independently call
`data_feed.get_market_data` and `analytics.build_features`. This means three round-trips
per `step()` call when a signal is found, and the feature vector used for risk evaluation
may differ from the one used for execution. This is a correctness bug in addition to
a performance issue.

**Fix:** Fetch and build features once per `step()` call at the top, then pass the result
through the state handlers. Refactor `step()` to a dispatcher pattern:

```python
async def step(self) -> Optional[TradeCandidate]:
    market_data = await self.data_feed.get_market_data(self.symbol)
    features = self.analytics.build_features(market_data)
    return await self._dispatch(features)
```

**Acceptance:** `data_feed.get_market_data` is called exactly once per `step()` invocation
in all states (verified by mock call count in tests).

---

## 5. `_build_order` hardcodes `quantity=1.0`

**Problem:** `Orchestrator._build_order` always sets `quantity=1.0` regardless of the
`RiskDecision.risk_multiplier` or `TradeCandidate` fields. This makes the risk layer
a no-op for sizing.

**Fix:** Pass the `RiskDecision` into `_build_order` and derive quantity from
`signal.risk_multiplier * decision.risk_multiplier`. Document the sizing formula in a
comment. The actual position-sizing logic belongs in `RiskPort`, so `_build_order` should
accept a pre-computed `quantity: float` parameter.

**Acceptance:** A test verifies that `_build_order` produces an order whose quantity
reflects the risk decision, not a hardcoded constant.

---

## 6. `Signal` model is unused and conflicts with `TradeCandidate`

**Problem:** `app/models/signal.py` defines a `Signal` model with `{symbol, direction,
strength, timestamp}`. The orchestrator and strategy port use `TradeCandidate` as the
signal type. `Signal` is never imported anywhere. Having two overlapping "signal" concepts
will confuse agents and developers.

**Fix:** Either:
- Delete `Signal` and use `TradeCandidate` everywhere, or
- Clarify the distinction (e.g., `Signal` = raw indicator output, `TradeCandidate` =
  enriched setup with risk fields) and document it in `AGENTS.md`.

**Acceptance:** No dead model files; every model is imported by at least one other module
or test.

---

## 7. `DataFeedPort.get_market_data` return type is untyped

**Problem:** `DataFeedPort.get_market_data` returns `Any` (no annotation). `FeatureEngine`
accepts `Any` and does runtime isinstance checks. This defeats the purpose of the port
abstraction and makes it impossible for agents to know what contract adapters must satisfy.

**Fix:** Define a `MarketBundle` TypedDict or dataclass:
```python
class MarketBundle(TypedDict):
    market: MarketSnapshot
    price_history: list[float]
    volume_history: list[float]
    oi_history: list[float]
    funding_history: list[float]
    liquidation_above: float
    liquidation_below: float
    onchain: OnChainSnapshot | None
    news: NewsImpactReport | None
```
Update `DataFeedPort` to return `MarketSnapshot | MarketBundle` and remove the
`isinstance` branching from `FeatureEngine._normalize_bundle`.

**Acceptance:** `mypy app/` reports no `Any`-typed return values on port methods.

---

## 8. Missing `.gitignore`

**Problem:** No `.gitignore` exists. Running `pip install -e .` or creating a virtualenv
will stage `__pycache__/`, `.egg-info/`, `venv/`, etc.

**Fix:** Create `.gitignore` with at minimum:
```
__pycache__/
*.pyc
*.pyo
*.egg-info/
dist/
build/
.venv/
venv/
.env
.env.*
.pytest_cache/
.coverage
htmlcov/
```

**Acceptance:** `git status` after `pip install -e .[dev]` shows no untracked
dependency artifacts.

---

## 9. Stub modules are missing entirely

**Problem:** `README.md` lists `app/strategy/`, `app/risk/`, `app/execution/`,
`app/feeds/`, and `app/telegram/` as planned modules. None of them exist, not even as
empty packages. Agents asked to implement these will create files in arbitrary locations.

**Fix:** Create the directory structure with `__init__.py` stubs and a `# TODO` comment
in each, so agents have a canonical location to work in:
```
app/strategy/__init__.py
app/risk/__init__.py
app/execution/__init__.py
app/feeds/__init__.py
app/telegram/__init__.py
```

**Acceptance:** `find app -name __init__.py` lists all eight package directories.

---

## 10. `devcontainer.json` does not install Python dependencies on startup

**Problem:** The dev container uses the universal image but has no `postCreateCommand`
to install the project. An agent starting a fresh environment must manually run
`pip install -e .[dev]` before any code works.

**Fix:** Add to `devcontainer.json`:
```json
"postCreateCommand": "pip install -e '.[dev]'"
```

**Acceptance:** After container creation, `pytest --collect-only` succeeds without
manual setup steps.

---

## Summary table

| # | Area | Severity | Effort |
|---|------|----------|--------|
| 1 | `__init__.py` missing | Blocker | 5 min |
| 2 | No declared dependencies | Blocker | 5 min |
| 3 | No tests | High | 2–4 h |
| 4 | Redundant data fetches in Orchestrator | High | 30 min |
| 5 | Hardcoded quantity in `_build_order` | High | 15 min |
| 6 | Dead `Signal` model | Medium | 10 min |
| 7 | Untyped port return values | Medium | 30 min |
| 8 | Missing `.gitignore` | Medium | 5 min |
| 9 | Stub directories absent | Low | 5 min |
| 10 | No `postCreateCommand` | Low | 5 min |
