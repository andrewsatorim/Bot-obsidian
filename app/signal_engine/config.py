"""Configuration for the private signal engine.

Loaded from a SEPARATE env file (``.env.signal``) with a SEPARATE env prefix
(``SIGNAL_``) and a SEPARATE Telegram token, so the private engine never shares
credentials or runtime config with the sellable main bot.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class SignalSettings(BaseSettings):
    # Universe to scan for setups (read-only: signal engine never trades these).
    symbols: list[str] = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
    # Default raised to 60s: a multi-timeframe scan issues several OHLCV requests
    # per symbol, so a tighter interval would hit exchange rate limits.
    scan_interval_sec: float = Field(default=60.0, gt=0)

    # --- Multi-timeframe architecture (sub-step 1) ----------------------------
    # ccxt-unified timeframe strings ("1h" == 60m, "1d" == D).
    #
    # Context layer: slow macro backdrop. Cached and refreshed at most once per
    # context_refresh_sec (NOT re-fetched every scan). The DAILY timeframe sets
    # the direction; the second (12h) only amplifies/dampens it (see context.py).
    context_timeframes: list[str] = ["1d", "12h"]
    # Evaluation panel: each of these casts a direction vote every scan. 5m is
    # deliberately NOT here — it is the entry timeframe only, not a trend vote.
    eval_timeframes: list[str] = ["15m", "30m", "1h", "4h"]
    # Setup timeframe: where the trade is detected (the strategy runs here). It
    # is intentionally also in eval_timeframes (it both finds the trade and votes).
    setup_timeframe: str = "15m"
    # Entry timeframe: short-term momentum / entry timing once a setup is found.
    entry_timeframe: str = "5m"
    ohlcv_limit: int = Field(default=100, gt=0)            # candles fetched per timeframe
    context_refresh_sec: float = Field(default=86400.0, gt=0)  # <= once per day

    # --- Setup quality weights (SOFT contribution, not hard gates) ------------
    # Final quality = sum(weight_i * score_i) / sum(weight_i over AVAILABLE i),
    # each score_i in 0..1. Coinglass factors drop out of the denominator when
    # their data is unavailable (the honest cap is preserved). Tuned on live data.
    weight_signal: float = Field(default=1.0, ge=0)        # strategy signal strength
    weight_regime: float = Field(default=1.0, ge=0)        # regime on the setup TF
    weight_liquidity: float = Field(default=1.0, ge=0)     # Coinglass liquidity zone
    weight_oi: float = Field(default=1.0, ge=0)            # Coinglass OI imbalance
    weight_eval_tf: float = Field(default=2.0, ge=0)       # eval-TF consensus (big)
    weight_context: float = Field(default=1.5, ge=0)       # D/12h macro context
    weight_entry: float = Field(default=0.5, ge=0)         # entry-TF momentum (light)
    context_neutral_score: float = Field(default=0.5, ge=0, le=1)  # score for a neutral context

    # Which strategy drives setup detection. Defaults to a walk-forward-robust
    # trend follower. Must be a key of app.signal_engine.setups.STRATEGY_FACTORIES.
    strategy_name: str = "TrendFollowing"

    # Setup selection thresholds.
    min_confidence: float = Field(default=0.4, ge=0, le=1)  # factor (a): signal strength
    min_quality: float = Field(default=0.5, ge=0, le=1)     # keep setups with quality >= this
    min_oi_imbalance: float = Field(default=0.0)            # factor (d): OI build threshold

    # Risk / sizing (informational only — engine never executes).
    account_equity: float = Field(default=10_000.0, gt=0)
    atr_mult: float = Field(default=1.5, gt=0)              # ATR stop multiplier
    rr_target: float = Field(default=2.0, gt=0)             # reward:risk for take-profit
    leverages: list[float] = [20.0, 30.0, 50.0]            # leverage scenarios to report (keep <= max_leverage)
    fee_pct: float = Field(default=0.0005, ge=0)           # taker fee per side (round-trip x2)

    # Hard cap on usable leverage. A setup is only sent if doubling the deposit
    # in one trade (x2) is achievable at leverage <= this; setups whose x2 needs
    # more (or is unreachable) are FILTERED OUT, not just annotated. The risk
    # block also never shows scenarios above this cap.
    max_leverage: float = Field(default=50.0, gt=0)

    # Coinglass (v4) — feeds the liquidation-heatmap and OI factors with real
    # data. If empty, those factors are reported as "data unavailable" (never
    # counted as matched) and setup quality is scored on the remaining factors.
    coinglass_api_key: str = ""

    # Private Telegram channel — distinct token/chat from the main bot.
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    log_level: str = "INFO"

    model_config = {
        "env_prefix": "SIGNAL_",
        "env_file": ".env.signal",
        "env_file_encoding": "utf-8",
    }
