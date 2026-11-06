"""Historical Market Data Downloader for QuantAI.

Acquires historical Binance Spot OHLCV candles across multiple timeframes,
stores them into the SQLite / TimescaleDB database, and exports to Parquet.
"""

import logging
from datetime import datetime, timezone
import os
from typing import List, Optional
import httpx
from quantai.common import pd
from quantai.config.settings import get_config
from quantai.ingestion.binance import BinanceMarketDataClient
from quantai.storage.db import get_db_manager, init_database
from quantai.storage.models import MarketCandle

logger = logging.getLogger("quantai.downloader")


class HistoricalDataDownloader:
    """Downloads and archives historical market candle data."""

    def __init__(self):
        self.config = get_config()
        self.client = BinanceMarketDataClient()
        self.db_manager = get_db_manager()

    def download_range(
        self,
        symbol: str = "BTC/USDT",
        timeframe: str = "5m",
        total_candles: int = 500,
    ) -> int:
        """Downloads historical candles in chunks of 100 up to total_candles."""
        init_database()
        logger.info(f"Downloading {total_candles} {timeframe} candles for {symbol}...")

        limit_per_call = 100
        fetched_count = 0
        all_candles = []

        while fetched_count < total_candles:
            chunk_size = min(limit_per_call, total_candles - fetched_count)
            candles = self.client.fetch_klines(symbol=symbol, interval=timeframe, limit=chunk_size)
            if not candles:
                break
            all_candles.extend(candles)
            fetched_count += len(candles)
            if len(candles) < chunk_size:
                break

        # Persist into database with deduplication
        saved_count = 0
        with self.db_manager.get_session() as session:
            for c in all_candles:
                exists = (
                    session.query(MarketCandle)
                    .filter(
                        MarketCandle.pair == c.symbol,
                        MarketCandle.timeframe == c.timeframe,
                        MarketCandle.timestamp == c.event_time,
                    )
                    .first()
                )
                if not exists:
                    rec = MarketCandle(
                        pair=c.symbol,
                        timeframe=c.timeframe,
                        timestamp=c.event_time,
                        open=c.open,
                        high=c.high,
                        low=c.low,
                        close=c.close,
                        volume=c.volume,
                        trades_count=c.trades_count,
                        ingestion_time=datetime.now(timezone.utc),
                    )
                    session.add(rec)
                    saved_count += 1

        logger.info(f"Successfully downloaded and persisted {saved_count} new candles for {symbol}.")
        return saved_count
