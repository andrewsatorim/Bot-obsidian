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

## Sending rules: x2 leverage filter + dedup

A passing `min_quality` setup is **not** automatically sent. Two gates run in
`engine.run_once`:

1. **x2 leverage filter (a filter, not text).** A setup is sent only if the
   deposit can be doubled in one trade (x2) at leverage **≤ `max_leverage`**
   (default **50**). The leverage needed is `1 / (target_move − round_trip_fee)`;
   if that exceeds the cap — or x2 is unreachable (`inf`) — the setup is
   **dropped**, never sent. In practice this needs a target move ≥ ~2%, i.e.
   **ATR ≳ 0.7% of price** at the default `atr_mult=1.5`, `rr_target=2`. The risk
   block only ever shows leverages ≤ `max_leverage`, and the x2 line is always a
   real capped value (`… ≈ x17 (≤50) …`).
2. **Edge-triggered dedup.** Each setup is keyed by `(symbol, direction)` and
   alerted **once when it appears**, not on every scan. The key re-arms when the
   setup disappears, so a later recurrence alerts again. This is what stops the
   same setup arriving in a batch every `scan_interval_sec`.

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
          tests/test_signal_engine_risk.py \
          tests/test_signal_engine_engine.py
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
