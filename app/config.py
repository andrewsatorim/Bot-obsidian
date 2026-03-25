from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Core
    symbol: str = "BTC/USDT"
    scan_interval_sec: float = 10.0
    cooldown_sec: float = 60.0

    # Risk
    max_position_pct: float = Field(default=0.02, ge=0.001, le=0.1)
    max_daily_loss_pct: float = Field(default=0.05, ge=0.01, le=0.2)
    atr_risk_multiplier: float = Field(default=1.5, gt=0)
    max_open_positions: int = Field(default=3, ge=1)
    min_confidence: float = Field(default=0.3, ge=0, le=1)
    account_equity: float = Field(default=10_000.0, gt=0)

    # Exchange
    exchange_id: str = "binance"
    exchange_api_key: str = ""
    exchange_api_secret: str = ""
    paper_trading: bool = True

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Storage
    storage_path: str = "data/bot_state.db"

    # Logging
    log_level: str = "INFO"

    model_config = {"env_prefix": "BOT_", "env_file": ".env", "env_file_encoding": "utf-8"}
