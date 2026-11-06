"""Universal Ingestion Data Contracts & Quality Models."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DataQualityStatus(str, Enum):
    VALID = "VALID"
    DEGRADED = "DEGRADED"
    STALE = "STALE"
    CORRUPT = "CORRUPT"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IngestionRecord(BaseModel):
    source: str
    event_time: datetime
    ingestion_time: datetime = Field(default_factory=utc_now)
    symbol: str
    data_type: str
    quality: DataQualityStatus = DataQualityStatus.VALID
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CandleData(IngestionRecord):
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    trades_count: int = 0


class TradeData(IngestionRecord):
    trade_id: str
    price: float
    amount: float
    side: str  # buy or sell
    is_maker: bool = False


class OrderBookDepth(IngestionRecord):
    best_bid: float
    best_ask: float
    spread: float
    bid_depth_10: float
    ask_depth_10: float
    bids: List[List[float]] = Field(default_factory=list)  # [[price, size], ...]
    asks: List[List[float]] = Field(default_factory=list)


class BlockchainTxData(IngestionRecord):
    tx_hash: str
    blockchain: str
    from_address: str
    to_address: str
    amount: float
    usd_value: float
    is_exchange_inflow: bool = False
    is_exchange_outflow: bool = False


class DerivativesData(IngestionRecord):
    funding_rate: float
    open_interest: float
    long_short_ratio: float
    liquidation_buy_usd: float = 0.0
    liquidation_sell_usd: float = 0.0
    futures_basis_bps: float = 0.0


class NewsSentimentData(IngestionRecord):
    title: str
    url: Optional[str] = None
    sentiment_score: float  # -1.0 to 1.0
    sentiment_label: str  # bullish, bearish, neutral
    impact_weight: float = 0.5

