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
    scan_interval_sec: float = Field(default=30.0, gt=0)

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
    leverages: list[float] = [20.0, 30.0, 40.0]            # leverage scenarios to report
    fee_pct: float = Field(default=0.0005, ge=0)           # taker fee per side (round-trip x2)

    # Private Telegram channel — distinct token/chat from the main bot.
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    log_level: str = "INFO"

    model_config = {
        "env_prefix": "SIGNAL_",
        "env_file": ".env.signal",
        "env_file_encoding": "utf-8",
    }
