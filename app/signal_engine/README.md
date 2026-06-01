# Signal Engine (private, Stage 6)

A **private** signal engine that scans the configured universe, scores setups,
computes honest leverage risk, and sends a **text-only** alert to a private
Telegram channel. It is intentionally separate from the sellable main bot.

## ⚠️ KNOWN LIMITATION — Coinglass not wired yet (do before real use)

Until a Coinglass heatmap / OI feed is wired into `scripts/run_signal_engine.py`,
the engine builds features from the **ccxt feed only**. That feed does not
populate the liquidation heatmap and often returns little/no open-interest
history, so:

- factor **(c) liquidity zone** (`liquidation_above` / `liquidation_below`) and
- factor **(d) OI imbalance** (`oi_delta` / `oi_trend`)

evaluate on **incomplete data**. When those fields are zero/empty the factors
read as *not matched*, which **depresses or distorts the setup quality score** —
in practice it tends to **overstate** quality for setups that only pass the
remaining factors. **Treat the quality % as provisional until Coinglass is
connected.** Tracked for Stage 6.6 (Coinglass + deploy). Do not run this against
real money for sizing decisions before that is done.

## Isolation contract (enforced by `tests/test_signal_engine_isolation.py`)

1. **No execution path.** This package never imports — directly or transitively —
   executors, orchestrators, or `ExecutionPort`. Its only side effect is Telegram
   text via `notifier.TelegramSignalNotifier`.
2. **One-way dependency.** Nothing in the main `app` package imports
   `app.signal_engine`. The whole engine is removable before a sale with:

   ```bash
   rm -rf app/signal_engine scripts/run_signal_engine.py .env.signal.example \
          tests/test_signal_engine_isolation.py \
          tests/test_signal_engine_setups.py \
          tests/test_signal_engine_risk.py
   ```

   Verified: after this cut the main package (`app.main`, `app.api`,
   orchestrator, executor) still imports and the main test suite stays green.

## Running

Separate process, separate config, separate Telegram token:

```bash
cp .env.signal.example .env.signal   # fill in SIGNAL_TELEGRAM_* (private bot)
python scripts/run_signal_engine.py
```

All configuration is env-driven via the `SIGNAL_` prefix (see `config.py`):
universe, scan interval, strategy choice, quality threshold, ATR/RR, leverages,
fees. No paths, IPs, or keys are hardcoded.
