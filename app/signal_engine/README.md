# Signal Engine (private, Stage 6)

A **private** signal engine that scans the configured universe, scores setups,
computes honest leverage risk, and sends a **text-only** alert to a private
Telegram channel. It is intentionally separate from the sellable main bot.

## Data sources & the Coinglass-dependent factors

Two of the four quality factors need data the plain ccxt feed does not provide:

- factor **(c) liquidity zone** — Coinglass liquidation heatmap
  (`liquidation_above` = shorts' liquidations, `liquidation_below` = longs'), and
- factor **(d) OI imbalance** — Coinglass realtime open interest.

**Coinglass (v4) is wired in `scripts/run_signal_engine.py`** and activates when
`SIGNAL_COINGLASS_API_KEY` is set (see `market_data.CoinglassProvider`).

**Honest fallback (no key, or a fetch error):** those two factors are reported as
`⚠️ данные недоступны` and **never counted toward setup quality** — they are
tri-state `None`, not a fabricated pass and not a misleading fail. Quality is
`matched / 4`, so without Coinglass the score is honestly **capped at 50%**
(only the signal + regime factors can fire) rather than overstated. Set the key
to get the full four-factor confirmation before relying on the quality % for
sizing decisions.

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
cp .env.signal.example .env.signal   # SIGNAL_TELEGRAM_* (private bot);
                                     # SIGNAL_COINGLASS_API_KEY for factors (c)/(d)
python scripts/run_signal_engine.py
```

All configuration is env-driven via the `SIGNAL_` prefix (see `config.py`):
universe, scan interval, strategy choice, quality threshold, ATR/RR, leverages,
fees. No paths, IPs, or keys are hardcoded.
