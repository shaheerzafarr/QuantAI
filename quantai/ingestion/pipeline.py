"""Unified Ingestion Pipeline with Deduplication, Persistence, and Health Monitoring."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from quantai.config.settings import get_config
from quantai.ingestion.binance import BinanceMarketDataClient
from quantai.ingestion.schema import CandleData, OrderBookDepth, DataQualityStatus
from quantai.storage.db import get_db_manager
from quantai.storage.models import MarketCandle, OrderBookSnapshot

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """Coordinates data acquisition across market, chain, and derivatives sources."""

    def __init__(self):
        self.config = get_config()
        self.binance_client = BinanceMarketDataClient()
        self.db_manager = get_db_manager()
        self.last_sync_times: Dict[str, datetime] = {}
        self.health_status: Dict[str, str] = {
            "binance_klines": "UNKNOWN",
            "binance_orderbook": "UNKNOWN",
            "database": "UNKNOWN",
        }

    def sync_candles(
        self,
        symbol: str = "BTC/USDT",
        timeframe: str = "5m",
        limit: int = 100,
    ) -> List[CandleData]:
        """Fetch and persist OHLCV candles with deduplication."""
        candles = self.binance_client.fetch_klines(symbol=symbol, interval=timeframe, limit=limit)
        if not candles:
            self.health_status["binance_klines"] = "DEGRADED"
            return []

        self.health_status["binance_klines"] = "HEALTHY"
        self.last_sync_times[f"{symbol}_{timeframe}"] = datetime.now(timezone.utc)

        # Persist to database
        try:
            with self.db_manager.get_session() as session:
                for c in candles:
                    # Check duplicate
                    existing = (
                        session.query(MarketCandle)
                        .filter(
                            MarketCandle.pair == c.symbol,
                            MarketCandle.timeframe == c.timeframe,
                            MarketCandle.timestamp == c.event_time,
                        )
                        .first()
                    )
                    if existing:
                        # Update close and volume
                        existing.high = max(existing.high, c.high)
                        existing.low = min(existing.low, c.low)
                        existing.close = c.close
                        existing.volume = c.volume
                    else:
                        new_candle = MarketCandle(
                            pair=c.symbol,
                            timeframe=c.timeframe,
                            timestamp=c.event_time,
                            open=c.open,
                            high=c.high,
                            low=c.low,
                            close=c.close,
                            volume=c.volume,
                            trades_count=c.trades_count,
                            ingestion_time=c.ingestion_time,
                        )
                        session.add(new_candle)
            self.health_status["database"] = "HEALTHY"
        except Exception as e:
            logger.error(f"Failed to persist candles to DB: {e}")
            self.health_status["database"] = "ERROR"

        return candles

    def sync_orderbook(self, symbol: str = "BTC/USDT") -> OrderBookDepth:
        """Fetch and persist order book snapshot."""
        depth = self.binance_client.fetch_orderbook(symbol=symbol)
        self.health_status["binance_orderbook"] = "HEALTHY"

        try:
            with self.db_manager.get_session() as session:
                snapshot = OrderBookSnapshot(
                    pair=depth.symbol,
                    timestamp=depth.event_time,
                    best_bid=depth.best_bid,
                    best_ask=depth.best_ask,
                    spread=depth.spread,
                    bid_depth_10=depth.bid_depth_10,
                    ask_depth_10=depth.ask_depth_10,
                    bids=depth.bids,
                    asks=depth.asks,
                    ingestion_time=depth.ingestion_time,
                )
                session.add(snapshot)
        except Exception as e:
            logger.error(f"Failed to persist orderbook: {e}")

        return depth

    def get_health(self) -> Dict[str, Any]:
        return {
            "statuses": self.health_status,
            "last_sync": {k: v.isoformat() for k, v in self.last_sync_times.items()},
        }
