"""Binance Real-Time WebSocket Streaming Client for QuantAI.

Connects to Binance Spot live WebSocket streams (klines, trades, depth)
with automatic exponential backoff reconnection, sub-second latency,
and event dispatching to the intelligence and execution layers.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
import aiohttp

from quantai.ingestion.schema import CandleData, DataQualityStatus

logger = logging.getLogger("quantai.ingestion.websocket")


class BinanceWebSocketClient:
    """Asynchronous real-time WebSocket client for Binance Spot."""

    WS_BASE_URL = "wss://stream.binance.com:9443"

    def __init__(
        self,
        pairs: Optional[List[str]] = None,
        timeframe: str = "5m",
        on_candle_update: Optional[Callable[[CandleData, bool], None]] = None,
        on_price_tick: Optional[Callable[[str, float], None]] = None,
    ):
        self.pairs = pairs or ["BTC/USDT", "ETH/USDT"]
        self.timeframe = timeframe
        self.on_candle_update = on_candle_update
        self.on_price_tick = on_price_tick
        self.running = False
        self._task: Optional[asyncio.Task] = None

        # Latest cache
        self.latest_prices: Dict[str, float] = {}
        self.latest_candles: Dict[str, CandleData] = {}

    def _build_combined_stream_url(self) -> str:
        """Constructs the multiplexed stream URL for configured pairs."""
        streams = []
        for pair in self.pairs:
            sym = pair.replace("/", "").lower()
            streams.append(f"{sym}@kline_{self.timeframe}")
            streams.append(f"{sym}@ticker")
        return f"{self.WS_BASE_URL}/stream?streams={'/'.join(streams)}"

    async def start(self):
        """Starts the real-time WebSocket streaming loop."""
        self.running = True
        logger.info(f"Connecting to Binance WebSocket stream for pairs: {self.pairs} ({self.timeframe})...")

        backoff_seconds = 1.0
        while self.running:
            url = self._build_combined_stream_url()
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(url, heartbeat=20.0) as ws:
                        logger.info("Connected to Binance Spot WebSocket stream.")
                        backoff_seconds = 1.0  # Reset backoff on successful connection

                        async for msg in ws:
                            if not self.running:
                                break
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    payload = json.loads(msg.data)
                                    self._handle_stream_message(payload)
                                except Exception as e:
                                    logger.error(f"Error handling WebSocket message: {e}")
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                logger.warning(f"WebSocket closed with type {msg.type}.")
                                break
            except asyncio.CancelledError:
                logger.info("WebSocket listener cancelled.")
                break
            except Exception as e:
                logger.warning(f"WebSocket connection error: {e}. Reconnecting in {backoff_seconds:.1f}s...")
                await asyncio.sleep(backoff_seconds)
                backoff_seconds = min(60.0, backoff_seconds * 2.0)

    def _handle_stream_message(self, payload: Dict[str, Any]):
        """Parses Binance multiplexed stream payloads (kline, ticker)."""
        stream_name = payload.get("stream", "")
        data = payload.get("data", {})

        # 1. Handle Kline Stream
        if "kline" in stream_name:
            k = data.get("k", {})
            sym_raw = data.get("s", "")
            # Convert BTCUSDT -> BTC/USDT
            pair = self._format_symbol(sym_raw)

            open_ts = datetime.fromtimestamp(k.get("t", 0) / 1000, tz=timezone.utc)
            is_candle_closed = bool(k.get("x", False))
            current_close = float(k.get("c", 0.0))

            candle = CandleData(
                source="binance_ws",
                event_time=open_ts,
                symbol=pair,
                data_type="candle",
                timeframe=k.get("i", self.timeframe),
                open=float(k.get("o", 0.0)),
                high=float(k.get("h", 0.0)),
                low=float(k.get("l", 0.0)),
                close=current_close,
                volume=float(k.get("v", 0.0)),
                trades_count=int(k.get("n", 0)),
                quality=DataQualityStatus.VALID,
            )

            self.latest_candles[pair] = candle
            self.latest_prices[pair] = current_close

            if self.on_candle_update:
                try:
                    self.on_candle_update(candle, is_candle_closed)
                except Exception as e:
                    logger.error(f"Error in on_candle_update callback: {e}")

        # 2. Handle 24hr Ticker Stream (for ultra-fast price updates)
        elif "ticker" in stream_name:
            sym_raw = data.get("s", "")
            pair = self._format_symbol(sym_raw)
            current_price = float(data.get("c", 0.0))
            self.latest_prices[pair] = current_price

            if self.on_price_tick:
                try:
                    self.on_price_tick(pair, current_price)
                except Exception as e:
                    logger.error(f"Error in on_price_tick callback: {e}")

    def _format_symbol(self, raw_symbol: str) -> str:
        """Converts raw exchange symbols like BTCUSDT to standard BTC/USDT."""
        for p in self.pairs:
            if p.replace("/", "").upper() == raw_symbol.upper():
                return p
        if raw_symbol.endswith("USDT"):
            base = raw_symbol[:-4]
            return f"{base}/USDT"
        return raw_symbol

    def stop(self):
        """Stops the WebSocket streamer gracefully."""
        self.running = False

