# Trading vectors: fast vs slow

The project runs two distinct, **multi-timeframe** decision vectors. Both read
the same kind of ccxt market data but sit at opposite ends of the timeframe
spectrum and serve different purposes. Their strategies are selected
**separately**, each backtested on its own timeframes.

> ⚠️ **Status.** The **fast vector** is implemented (`app/signal_engine/`). The
> **slow vector below is a TARGET specification — NOT yet implemented.** The main
> trading engine does not run this timeframe hierarchy today (see
> "Current state vs target"). Read the slow-vector section as the goal, not as a
> description of existing code.

| | **Fast vector** (implemented) | **Slow vector** (planned) |
|---|---|---|
| Code | `app/signal_engine/` (private) | `app/core`, orchestrator, execution (sellable) |
| Output | Telegram **text signal only** (no execution) | **Live trade execution** |
| Bias | shorter timeframes, intraday impulses | higher timeframes, hold the senior trend |
| Side focus | short positions | long positions |
| Evaluation TFs | `15m`, `30m`, `1h`, `4h` | `1h` (60m), `4h`, `12h`, `1d` (D) |
| Context (cached) | `1d` + `12h` (≤1×/day) | senior structure/trend (the high TFs above) |
| Setup TF | `15m` | `30m` |
| Entry TF | `3m`/`5m` (config; default `5m`) | `30m` |
| Strategy source | `SIGNAL_STRATEGY_NAME` (default `TrendFollowing`) | main-bot config |

**Key difference.** The fast vector catches short impulses on the lower
timeframes; the slow vector opens and holds a position aligned with the senior
trend. They are not two settings of one engine — they are separate engines.

---

## Fast vector — signal engine (private)

- **Location:** `app/signal_engine/` — a private, isolated, removable module.
  Its only side effect is a Telegram text message; it has no execution path and
  never imports the executor/orchestrator (enforced by
  `tests/test_signal_engine_isolation.py`).
- **Timeframe hierarchy (config-driven, `SIGNAL_*`):**
  - Context layer `1d` + `12h` — slow macro backdrop, **cached** and refreshed at
    most once per `SIGNAL_CONTEXT_REFRESH_SEC` (default a day). The daily sets the
    direction; 12h amplifies/dampens it (never flips). Not re-fetched every scan.
  - Evaluation panel `15m, 30m, 1h, 4h` — each casts a direction vote every scan
    (consensus). `5m` is deliberately the entry timeframe only, not a voter.
  - Setup TF `15m` — where the trade is detected (the strategy runs here).
  - Entry TF `5m` (or `3m` via `SIGNAL_ENTRY_TIMEFRAME`) — short-term momentum.
- **Center of gravity:** the lower timeframes — built to spot short intraday
  impulses, oriented to **short** positions.
- **Quality:** a soft, weighted blend (`setups.compute_quality`) of the strategy
  signal, setup-TF regime, eval-TF consensus, D/12h context and entry momentum,
  plus the Coinglass liquidity/OI factors when available. Disagreement lowers the
  score; it is not a hard gate.

## Slow vector — main trading engine (sellable) — TARGET, not yet implemented

> This section describes the **intended** design. It is **not** what the code
> does today — see "Current state vs target" immediately below.

- **Location:** `app/core` + orchestrator + execution — the main bot that places
  real trades and is the product sold to customers.
- **Timeframe hierarchy (shifted to the higher timeframes):**
  - Evaluation TFs `1h` (60m), `4h`, `12h`, `1d` (D).
  - Entry TF `30m`.
  - Setup confirmation leans on the senior structure/trend (`60m/4h/12h/D`).
- **Center of gravity:** the higher timeframes — opens and **holds** a position
  aligned with the senior trend, oriented to **long** positions.

### Current state vs target

Verified from code (read-only, June 2026). The slow vector's multi-timeframe
design is **not implemented**; the main engine currently runs:

| Aspect | Target (above) | Actual code today |
|---|---|---|
| Timeframe(s) | `60m/4h/12h/D` eval, `30m` entry | **single `1m`** (`app/feeds/ccxt_feed.py:42`, hardcoded) |
| Multi-TF / context cache | yes | **none** (no multi-TF logic in `app/core`) |
| Side | long-centric | **long *and* short** (`app/core/orchestrator.py`) |
| Strategy | one, backtested on `30m` + confirmation | **fusion of 6** (`StrategyFusion`, `app/main.py`) |
| Scan interval | matched to the senior TF | **10s** (`app/config.py`) |

Data path today: `orchestrator.step()` → one `data_feed.get_market_data(symbol)`
(1m, 100 bars) → `build_features` → `strategy.generate_signal`. No higher-
timeframe panel, no `30m` entry layer, no context layer.

So the multi-timeframe architecture exists **only in the fast vector** so far.
Closing this gap (shifting the main engine to `60m/4h/12h/D` + `30m` entry,
long-centric, single strategy) is future work — it touches live trading-engine
logic and must not be started without an explicit decision.

---

## Strategies are chosen separately

The strategy for each vector is selected **independently**, by backtests run on
that vector's own timeframes:

- **Fast vector** — strategy backtested on the lower timeframes (`5m`–`15m`),
  set via `SIGNAL_STRATEGY_NAME` (default `TrendFollowing`).
- **Slow vector** — strategy backtested on `30m` with confirmation from
  `60m/4h/12h/D`, configured in the main bot.

There is no shared "one best strategy": each vector runs the strategy proven on
its own horizon. (As of this writing the two selections are independent config
values; the fast vector's choice is not auto-derived from any ranking.)
