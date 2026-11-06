"""Database Schema & Models for QuantAI's 30 Core Data Domains."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Boolean,
    Text,
    JSON,
    Index,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# 1. Assets
class Asset(Base):
    __tablename__ = "assets"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(32), unique=True, nullable=False, index=True)
    base_asset = Column(String(16), nullable=False)
    quote_asset = Column(String(16), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)


# 2. Exchanges
class ExchangeRecord(Base):
    __tablename__ = "exchanges"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False)
    market_type = Column(String(32), default="spot")
    is_connected = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)


# 3. Market Candles (OHLCV)
class MarketCandle(Base):
    __tablename__ = "market_candles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    pair = Column(String(32), nullable=False, index=True)
    timeframe = Column(String(16), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    trades_count = Column(Integer, default=0)
    ingestion_time = Column(DateTime, default=utc_now)

    __table_args__ = (
        Index("idx_candle_pair_tf_ts", "pair", "timeframe", "timestamp", unique=True),
    )


# 4. Market Trades
class MarketTrade(Base):
    __tablename__ = "market_trades"
    id = Column(Integer, primary_key=True, autoincrement=True)
    pair = Column(String(32), nullable=False, index=True)
    trade_id = Column(String(64), nullable=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    price = Column(Float, nullable=False)
    amount = Column(Float, nullable=False)
    side = Column(String(8), nullable=False)  # 'buy' or 'sell'
    is_maker = Column(Boolean, default=False)
    ingestion_time = Column(DateTime, default=utc_now)


# 5. Orderbook Snapshots
class OrderBookSnapshot(Base):
    __tablename__ = "orderbook_snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    pair = Column(String(32), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    best_bid = Column(Float, nullable=False)
    best_ask = Column(Float, nullable=False)
    spread = Column(Float, nullable=False)
    bid_depth_10 = Column(Float, nullable=False)
    ask_depth_10 = Column(Float, nullable=False)
    bids = Column(JSON, nullable=True)
    asks = Column(JSON, nullable=True)
    ingestion_time = Column(DateTime, default=utc_now)


# 6. Orderflow Features
class OrderFlowFeature(Base):
    __tablename__ = "orderflow_features"
    id = Column(Integer, primary_key=True, autoincrement=True)
    pair = Column(String(32), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    timeframe = Column(String(16), default="5m")
    bid_ask_imbalance = Column(Float, default=0.0)
    cumulative_volume_delta = Column(Float, default=0.0)
    aggressive_buy_vol = Column(Float, default=0.0)
    aggressive_sell_vol = Column(Float, default=0.0)
    absorption_ratio = Column(Float, default=0.0)
    estimated_slippage_bps = Column(Float, default=0.0)
    created_at = Column(DateTime, default=utc_now)


# 7. Wallet Addresses & 8. Labels
class WalletAddress(Base):
    __tablename__ = "wallet_addresses"
    id = Column(Integer, primary_key=True, autoincrement=True)
    address = Column(String(128), unique=True, nullable=False, index=True)
    blockchain = Column(String(32), nullable=False, default="bitcoin")  # 'bitcoin', 'ethereum'
    entity_name = Column(String(128), nullable=True)
    category = Column(String(64), default="unknown")  # exchange, whale, smart_money, market_maker
    attribution_confidence = Column(Float, default=0.5)
    first_seen = Column(DateTime, default=utc_now)
    last_active = Column(DateTime, default=utc_now)


# 9. Wallet Transactions
class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tx_hash = Column(String(128), unique=True, nullable=False, index=True)
    blockchain = Column(String(32), nullable=False)
    from_address = Column(String(128), nullable=False, index=True)
    to_address = Column(String(128), nullable=False, index=True)
    asset = Column(String(16), nullable=False)
    amount = Column(Float, nullable=False)
    usd_value = Column(Float, nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    ingestion_time = Column(DateTime, default=utc_now)


# 10. Whale Events
class WhaleEvent(Base):
    __tablename__ = "whale_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(64), nullable=False)  # accumulation, distribution, exchange_inflow, exchange_outflow
    asset = Column(String(16), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    usd_value = Column(Float, nullable=False)
    source_wallet = Column(String(128), nullable=True)
    dest_wallet = Column(String(128), nullable=True)
    signal_bias = Column(String(16), nullable=False)  # bullish, bearish, neutral
    confidence = Column(Float, default=0.7)
    timestamp = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=utc_now)


# 11. Wallet Performance
class WalletPerformance(Base):
    __tablename__ = "wallet_performance"
    id = Column(Integer, primary_key=True, autoincrement=True)
    wallet_address = Column(String(128), unique=True, nullable=False, index=True)
    total_trades = Column(Integer, default=0)
    win_rate = Column(Float, default=0.0)
    profit_factor = Column(Float, default=0.0)
    realized_pnl_usd = Column(Float, default=0.0)
    avg_holding_hours = Column(Float, default=0.0)
    max_drawdown = Column(Float, default=0.0)
    smart_money_score = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=utc_now)


# 12. Derivatives Metrics
class DerivativesMetric(Base):
    __tablename__ = "derivatives_metrics"
    id = Column(Integer, primary_key=True, autoincrement=True)
    pair = Column(String(32), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    funding_rate = Column(Float, default=0.0)
    open_interest = Column(Float, default=0.0)
    long_short_ratio = Column(Float, default=1.0)
    liquidation_buy_usd = Column(Float, default=0.0)
    liquidation_sell_usd = Column(Float, default=0.0)
    futures_basis_bps = Column(Float, default=0.0)
    ingestion_time = Column(DateTime, default=utc_now)


# 13. News Articles & 14. Sentiment Signals
class NewsArticle(Base):
    __tablename__ = "news_articles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(256), nullable=False)
    source = Column(String(64), nullable=False)
    url = Column(String(512), nullable=True)
    published_at = Column(DateTime, nullable=False, index=True)
    sentiment_score = Column(Float, default=0.0)  # -1.0 to +1.0
    sentiment_label = Column(String(16), default="neutral")
    impact_weight = Column(Float, default=0.5)
    entities = Column(JSON, nullable=True)
    ingestion_time = Column(DateTime, default=utc_now)


# 15. Macro Events
class MacroEvent(Base):
    __tablename__ = "macro_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    indicator_name = Column(String(64), nullable=False, index=True)  # FED_RATE, CPI, DXY, SP500
    actual_value = Column(Float, nullable=False)
    forecast_value = Column(Float, nullable=True)
    previous_value = Column(Float, nullable=True)
    surprise_pct = Column(Float, default=0.0)
    impact_rating = Column(String(16), default="medium")
    timestamp = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=utc_now)


# 16. Technical Features & 17. Quantitative Features & 18. Market Regimes
class TechnicalFeature(Base):
    __tablename__ = "technical_features"
    id = Column(Integer, primary_key=True, autoincrement=True)
    pair = Column(String(32), nullable=False, index=True)
    timeframe = Column(String(16), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    rsi_14 = Column(Float, nullable=True)
    macd = Column(Float, nullable=True)
    macd_signal = Column(Float, nullable=True)
    macd_hist = Column(Float, nullable=True)
    ema_20 = Column(Float, nullable=True)
    ema_50 = Column(Float, nullable=True)
    ema_200 = Column(Float, nullable=True)
    bb_upper = Column(Float, nullable=True)
    bb_lower = Column(Float, nullable=True)
    bb_width = Column(Float, nullable=True)
    atr_14 = Column(Float, nullable=True)
    vwap = Column(Float, nullable=True)
    regime = Column(String(32), default="ranging")  # trending_bull, trending_bear, ranging, volatile
    created_at = Column(DateTime, default=utc_now)


# 19. Model Predictions & 20. Model Versions
class ModelPrediction(Base):
    __tablename__ = "model_predictions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    model_name = Column(String(64), nullable=False, index=True)
    model_version = Column(String(32), nullable=False)
    pair = Column(String(32), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    target_horizon = Column(String(16), default="1h")
    predicted_class = Column(String(16), nullable=False)  # BUY, SELL, HOLD
    calibrated_probability = Column(Float, nullable=False)
    expected_return_bps = Column(Float, default=0.0)
    raw_output = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utc_now)


# 21. Research Experiments & 22. Strategy Definitions & 23. Strategy Results
class StrategyResult(Base):
    __tablename__ = "strategy_results"
    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_name = Column(String(64), nullable=False, index=True)
    version = Column(String(32), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    win_rate = Column(Float, default=0.0)
    profit_factor = Column(Float, default=0.0)
    sharpe_ratio = Column(Float, default=0.0)
    deflated_sharpe = Column(Float, default=0.0)
    max_drawdown = Column(Float, default=0.0)
    total_trades = Column(Integer, default=0)
    net_pnl_pct = Column(Float, default=0.0)
    status = Column(String(32), default="candidate")  # research, backtest, paper, approved
    parameters = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utc_now)


# 24. Trading Signals & 25. Trade Decisions
class TradeDecisionRecord(Base):
    __tablename__ = "trade_decisions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    pair = Column(String(32), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    action = Column(String(16), nullable=False)  # BUY, SELL, HOLD, NO_TRADE
    confidence = Column(Float, nullable=False)
    expected_return_bps = Column(Float, default=0.0)
    expected_risk_bps = Column(Float, default=0.0)
    supporting_evidence = Column(JSON, nullable=True)
    contradictory_evidence = Column(JSON, nullable=True)
    risk_status = Column(String(32), default="approved")  # approved, vetoed_max_dd, vetoed_exposure
    explanation = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)


# 26. Trades & 27. Orders & 28. Portfolio Snapshots
class TradeRecord(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True, autoincrement=True)
    pair = Column(String(32), nullable=False, index=True)
    order_id = Column(String(64), unique=True, nullable=False)
    side = Column(String(8), nullable=False)  # buy, sell
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    amount = Column(Float, nullable=False)
    fee_paid = Column(Float, default=0.0)
    slippage_bps = Column(Float, default=0.0)
    realized_pnl = Column(Float, default=0.0)
    realized_pnl_pct = Column(Float, default=0.0)
    open_time = Column(DateTime, nullable=False)
    close_time = Column(DateTime, nullable=True)
    status = Column(String(16), default="open")  # open, closed, cancelled
    is_dry_run = Column(Boolean, default=True)


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    total_balance_usd = Column(Float, nullable=False)
    available_balance_usd = Column(Float, nullable=False)
    active_exposure_usd = Column(Float, default=0.0)
    unrealized_pnl_usd = Column(Float, default=0.0)
    daily_drawdown_pct = Column(Float, default=0.0)
    total_drawdown_pct = Column(Float, default=0.0)
    positions = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utc_now)


# 29. Risk Events & 30. System Events
class RiskEvent(Base):
    __tablename__ = "risk_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(64), nullable=False)  # VETO, CIRCUIT_BREAKER, EMERGENCY_HALT
    severity = Column(String(16), default="warning")  # info, warning, critical
    reason = Column(Text, nullable=False)
    details = Column(JSON, nullable=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=utc_now)


class SystemEvent(Base):
    __tablename__ = "system_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    subsystem = Column(String(64), nullable=False)
    level = Column(String(16), default="INFO")
    message = Column(Text, nullable=False)
    payload = Column(JSON, nullable=True)
    timestamp = Column(DateTime, nullable=False, index=True)
