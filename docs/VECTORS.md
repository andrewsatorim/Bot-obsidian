# Trading vectors: fast vs slow

The project runs two distinct, **multi-timeframe** decision vectors. Both read
the same kind of ccxt market data but sit at opposite ends of the timeframe
spectrum and serve different purposes. Their strategies are selected
**separately**, each backtested on its own timeframes.

| | **Fast vector** | **Slow vector** |
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

## Slow vector — main trading engine (sellable)

- **Location:** `app/core` + orchestrator + execution — the main bot that places
  real trades and is the product sold to customers.
- **Timeframe hierarchy (shifted to the higher timeframes):**
  - Evaluation TFs `1h` (60m), `4h`, `12h`, `1d` (D).
  - Entry TF `30m`.
  - Setup confirmation leans on the senior structure/trend (`60m/4h/12h/D`).
- **Center of gravity:** the higher timeframes — opens and **holds** a position
  aligned with the senior trend, oriented to **long** positions.

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
