"""Core Configuration Models and Settings for QuantAI."""

import os
from enum import Enum
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field


def _load_dotenv(filepath: str = ".env"):
    if not os.path.exists(filepath):
        return
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass


class ExecutionMode(str, Enum):
    DRY_RUN = "dry_run"
    PAPER = "paper"
    BACKTEST = "backtest"
    LIVE = "live"


class ExchangeConfig(BaseModel):
    name: str = "binance"
    market_type: str = "spot"
    pairs: List[str] = Field(default_factory=lambda: ["BTC/USDT", "ETH/USDT"])
    timeframes: List[str] = Field(default_factory=lambda: ["1m", "5m", "15m", "1h", "4h", "1d"])
    primary_timeframe: str = "5m"
    base_currency: str = "USDT"
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    rate_limit_per_minute: int = 1200
    orderbook_depth: int = 50
    poll_interval_seconds: float = 2.0


class StorageConfig(BaseModel):
    database_url: str = "sqlite:///user_data/quantai.db"
    timescale_url: Optional[str] = None
    redis_url: Optional[str] = "redis://localhost:6379/0"
    parquet_storage_path: str = "user_data/data/parquet"
    models_dir: str = "user_data/models"


class RiskConfig(BaseModel):
    max_risk_per_trade_pct: float = Field(default=0.01, description="1% risk per trade")
    max_portfolio_exposure_pct: float = Field(default=0.50, description="Max 50% capital deployed")
    max_daily_loss_pct: float = Field(default=0.02, description="2% daily drawdown limit")
    max_total_drawdown_pct: float = Field(default=0.06, description="6% max drawdown circuit breaker")
    stop_loss_pct: float = Field(default=0.015, description="1.5% fixed or trailing stop")
    take_profit_pct: float = Field(default=0.035, description="3.5% default take profit")
    kelly_fraction: float = Field(default=0.35, description="Fractional Kelly multiplier")
    emergency_shutdown_enabled: bool = True
    enforce_circuit_breakers: bool = True
    min_risk_reward_ratio: float = 1.8


class WhaleConfig(BaseModel):
    btc_whale_usd_threshold: float = 500_000.0
    eth_whale_usd_threshold: float = 250_000.0
    smart_money_min_win_rate: float = 0.58
    smart_money_min_profit_factor: float = 1.45
    min_tracked_trades: int = 15
    exchange_cluster_confidence_threshold: float = 0.80


class IntelligenceConfig(BaseModel):
    whale: WhaleConfig = Field(default_factory=WhaleConfig)
    feature_lookback_candles: int = 200
    orderflow_imbalance_threshold: float = 0.65
    funding_rate_extreme_threshold: float = 0.0005
    sentiment_drift_threshold: float = 0.25
    macro_lookback_days: int = 90


class QuantAIConfig(BaseModel):
    app_name: str = "QuantAI"
    version: str = "1.0.0"
    environment: str = "development"
    execution_mode: ExecutionMode = ExecutionMode.DRY_RUN
    exchange: ExchangeConfig = Field(default_factory=ExchangeConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    intelligence: IntelligenceConfig = Field(default_factory=IntelligenceConfig)
    api_host: str = "0.0.0.0"
    api_port: int = 8000


_default_config: Optional[QuantAIConfig] = None


def get_config() -> QuantAIConfig:
    global _default_config
    if _default_config is None:
        _load_dotenv()
        cfg = QuantAIConfig()
        
        # Override with environment variables if available
        if "BINANCE_API_KEY" in os.environ and os.environ["BINANCE_API_KEY"]:
            cfg.exchange.api_key = os.environ["BINANCE_API_KEY"]
        if "BINANCE_API_SECRET" in os.environ and os.environ["BINANCE_API_SECRET"]:
            cfg.exchange.api_secret = os.environ["BINANCE_API_SECRET"]
        if "DATABASE_URL" in os.environ and os.environ["DATABASE_URL"]:
            cfg.storage.database_url = os.environ["DATABASE_URL"]
        if "REDIS_URL" in os.environ and os.environ["REDIS_URL"]:
            cfg.storage.redis_url = os.environ["REDIS_URL"]
        if "EXECUTION_MODE" in os.environ and os.environ["EXECUTION_MODE"]:
            mode_str = os.environ["EXECUTION_MODE"].lower()
            if mode_str in [m.value for m in ExecutionMode]:
                cfg.execution_mode = ExecutionMode(mode_str)
        if "MAX_DAILY_LOSS_PCT" in os.environ:
            try:
                cfg.risk.max_daily_loss_pct = float(os.environ["MAX_DAILY_LOSS_PCT"])
            except ValueError:
                pass
        if "MAX_TOTAL_DRAWDOWN_PCT" in os.environ:
            try:
                cfg.risk.max_total_drawdown_pct = float(os.environ["MAX_TOTAL_DRAWDOWN_PCT"])
            except ValueError:
                pass
                
        _default_config = cfg
    return _default_config

