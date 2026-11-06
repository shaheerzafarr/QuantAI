"""QuantAI Ingestion Package."""

from quantai.ingestion.schema import (
    DataQualityStatus,
    CandleData,
    TradeData,
    OrderBookDepth,
    BlockchainTxData,
    DerivativesData,
    NewsSentimentData,
)
from quantai.ingestion.binance import BinanceMarketDataClient
from quantai.ingestion.pipeline import IngestionPipeline

__all__ = [
    "DataQualityStatus",
    "CandleData",
    "TradeData",
    "OrderBookDepth",
    "BlockchainTxData",
    "DerivativesData",
    "NewsSentimentData",
    "BinanceMarketDataClient",
    "IngestionPipeline",
]

