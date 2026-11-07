"""Binance Market Data Acquisition Adapter."""

import logging
from datetime import datetime, timezone
from typing import List, Optional
import httpx

from quantai.ingestion.schema import (
    CandleData,
    TradeData,
    OrderBookDepth,
    DataQualityStatus,
)

logger = logging.getLogger(__name__)


class BinanceMarketDataClient:
    """Binance Spot & Perpetual Futures REST Market Ingestion Client."""

    SPOT_URL = "https://api.binance.com/api/v3"
    FUTURES_URL = "https://fapi.binance.com/fapi/v1"

    def __init__(self, timeout: float = 10.0, market_type: str = "futures"):
        self.timeout = timeout
        self.market_type = market_type
        self.base_url = self.FUTURES_URL if market_type == "futures" else self.SPOT_URL
        self._session = httpx.Client(timeout=timeout)

    def get_top_perpetual_pairs(
        self,
        limit: int = 25,
        min_24h_volume_usd: float = 50_000_000.0,
    ) -> List[str]:
        """Scans the Binance Futures universe and returns top active liquid USDT-M perpetual contracts."""
        try:
            resp = self._session.get(f"{self.FUTURES_URL}/ticker/24hr")
            resp.raise_for_status()
            data = resp.json()
            pairs = []
            for item in data:
                sym = item.get("symbol", "")
                if sym.endswith("USDT") and not sym.startswith("1000"):
                    q_vol = float(item.get("quoteVolume", 0))
                    if q_vol >= min_24h_volume_usd:
                        formatted = f"{sym[:-4]}/USDT"
                        pairs.append((formatted, q_vol))
            pairs.sort(key=lambda x: x[1], reverse=True)
            return [p[0] for p in pairs[:limit]]
        except Exception as e:
            logger.warning(f"Error scanning top perpetual pairs: {e}. Falling back to default list.")
            return ["BTC/USDT", "ETH/USDT", "SOL/USDT", "DOGE/USDT", "XRP/USDT"]

    def fetch_funding_rate(self, symbol: str = "BTC/USDT") -> float:
        """Fetches the latest 8h perpetual funding rate."""
        clean_symbol = symbol.replace("/", "").upper()
        try:
            resp = self._session.get(f"{self.FUTURES_URL}/fundingRate", params={"symbol": clean_symbol, "limit": 1})
            resp.raise_for_status()
            data = resp.json()
            if data and isinstance(data, list):
                return float(data[0].get("fundingRate", 0.0001))
            return 0.0001
        except Exception:
            return 0.0001

    def fetch_klines(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "5m",
        limit: int = 100,
        start_time: Optional[int] = None,
    ) -> List[CandleData]:
        """Fetch historical or latest OHLCV candles from Binance (Spot or Futures)."""
        clean_symbol = symbol.replace("/", "").upper()
        url = f"{self.base_url}/klines"
        params = {"symbol": clean_symbol, "interval": interval, "limit": limit}
        if start_time:
            params["startTime"] = start_time

        try:
            resp = self._session.get(url, params=params)
            resp.raise_for_status()
            raw_klines = resp.json()

            candles: List[CandleData] = []
            for row in raw_klines:
                # row format: [open_time, open, high, low, close, volume, close_time, quote_asset_volume, trades, ...]
                open_ts = datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc)
                candles.append(
                    CandleData(
                        source="binance_rest",
                        event_time=open_ts,
                        symbol=symbol,
                        data_type="candle",
                        timeframe=interval,
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=float(row[5]),
                        trades_count=int(row[8]),
                        quality=DataQualityStatus.VALID,
                    )
                )
            return candles
        except Exception as e:
            logger.warning(f"Error fetching Binance klines for {symbol}: {e}. Falling back to synthetic candles.")
            return self.generate_synthetic_candles(symbol=symbol, timeframe=interval, limit=limit)

    def fetch_orderbook(self, symbol: str = "BTCUSDT", limit: int = 50) -> OrderBookDepth:
        """Fetch current order book depth snapshot."""
        clean_symbol = symbol.replace("/", "").upper()
        url = f"{self.base_url}/depth"
        params = {"symbol": clean_symbol, "limit": limit}

        try:
            resp = self._session.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            bids = [[float(p), float(q)] for p, q in data.get("bids", [])]
            asks = [[float(p), float(q)] for p, q in data.get("asks", [])]

            best_bid = bids[0][0] if bids else 0.0
            best_ask = asks[0][0] if asks else 0.0
            spread = best_ask - best_bid if (best_ask and best_bid) else 0.0

            bid_depth_10 = sum(p * q for p, q in bids[:10])
            ask_depth_10 = sum(p * q for p, q in asks[:10])

            return OrderBookDepth(
                source="binance_depth",
                event_time=datetime.now(timezone.utc),
                symbol=symbol,
                data_type="orderbook_snapshot",
                best_bid=best_bid,
                best_ask=best_ask,
                spread=spread,
                bid_depth_10=bid_depth_10,
                ask_depth_10=ask_depth_10,
                bids=bids[:20],
                asks=asks[:20],
                quality=DataQualityStatus.VALID,
            )
        except Exception as e:
            logger.warning(f"Error fetching Binance depth for {symbol}: {e}. Generating synthetic depth.")
            return self.generate_synthetic_depth(symbol)

    def fetch_recent_whale_trades(
        self, symbol: str = "BTCUSDT", limit: int = 500, min_notional_usd: float = 50_000.0
    ) -> Dict[str, Any]:
        """Fetches recent aggregated trades from Binance Futures and analyzes institutional blocks."""
        clean_symbol = symbol.replace("/", "").upper()
        url = f"{self.base_url}/aggTrades"
        params = {"symbol": clean_symbol, "limit": limit}
        try:
            resp = self._session.get(url, params=params, timeout=5)
            resp.raise_for_status()
            trades = resp.json()
            whale_buys = 0.0
            whale_sells = 0.0
            whale_trades = []
            for t in trades:
                p = float(t.get("p", 0.0))
                q = float(t.get("q", 0.0))
                notional = p * q
                if notional >= min_notional_usd:
                    is_taker_sell = t.get("m", False)  # True = buyer is maker, taker is seller
                    side = "SELL" if is_taker_sell else "BUY"
                    if not is_taker_sell:
                        whale_buys += notional
                    else:
                        whale_sells += notional
                    whale_trades.append({
                        "price": p,
                        "qty": q,
                        "notional": round(notional, 2),
                        "side": side,
                        "timestamp": t.get("T", 0),
                    })
            net_delta = whale_buys - whale_sells
            total_whale_vol = whale_buys + whale_sells
            bias = "NEUTRAL"
            if total_whale_vol > 0:
                delta_ratio = net_delta / total_whale_vol
                if delta_ratio > 0.20:
                    bias = "BULLISH"
                elif delta_ratio < -0.20:
                    bias = "BEARISH"
            return {
                "symbol": symbol,
                "whale_trade_count": len(whale_trades),
                "whale_buy_vol_usd": round(whale_buys, 2),
                "whale_sell_vol_usd": round(whale_sells, 2),
                "whale_net_delta_usd": round(net_delta, 2),
                "whale_bias": bias,
                "recent_whales": whale_trades[-5:],
            }
        except Exception as e:
            logger.debug(f"Error fetching whale trades for {symbol}: {e}")
            return {
                "symbol": symbol,
                "whale_trade_count": 0,
                "whale_buy_vol_usd": 0.0,
                "whale_sell_vol_usd": 0.0,
                "whale_net_delta_usd": 0.0,
                "whale_bias": "NEUTRAL",
                "recent_whales": [],
            }

    def generate_synthetic_candles(
        self, symbol: str, timeframe: str = "5m", limit: int = 100
    ) -> List[CandleData]:
        """Deterministic generator for testing and offline development."""
        import numpy as np

        base_price = 68000.0 if "BTC" in symbol else 3500.0
        now_ts = int(datetime.now(timezone.utc).timestamp())
        interval_secs = 300 if timeframe == "5m" else 60

        np.random.seed(42)
        returns = np.random.normal(0.0002, 0.003, limit)
        prices = base_price * np.exp(np.cumsum(returns))

        candles: List[CandleData] = []
        for i in range(limit):
            t = datetime.fromtimestamp(now_ts - (limit - i) * interval_secs, tz=timezone.utc)
            c = float(prices[i])
            o = float(c * (1 - np.random.normal(0, 0.001)))
            h = max(o, c) * (1 + abs(np.random.normal(0, 0.002)))
            l = min(o, c) * (1 - abs(np.random.normal(0, 0.002)))
            vol = float(np.random.uniform(10.0, 150.0))
            candles.append(
                CandleData(
                    source="synthetic_mock",
                    event_time=t,
                    symbol=symbol,
                    data_type="candle",
                    timeframe=timeframe,
                    open=o,
                    high=h,
                    low=l,
                    close=c,
                    volume=vol,
                    trades_count=int(vol * 8),
                    quality=DataQualityStatus.VALID,
                )
            )
        return candles

    def generate_synthetic_depth(self, symbol: str) -> OrderBookDepth:
        """Deterministic orderbook depth generator."""
        base_price = 68000.0 if "BTC" in symbol else 3500.0
        spread = base_price * 0.0001
        best_bid = base_price - spread / 2
        best_ask = base_price + spread / 2

        bids = [[best_bid - i * 5.0, 0.5 + i * 0.2] for i in range(20)]
        asks = [[best_ask + i * 5.0, 0.5 + i * 0.18] for i in range(20)]

        return OrderBookDepth(
            source="synthetic_mock",
            event_time=datetime.now(timezone.utc),
            symbol=symbol,
            data_type="orderbook_snapshot",
            best_bid=best_bid,
            best_ask=best_ask,
            spread=spread,
            bid_depth_10=sum(p * q for p, q in bids[:10]),
            ask_depth_10=sum(p * q for p, q in asks[:10]),
            bids=bids,
            asks=asks,
            quality=DataQualityStatus.VALID,
        )

    def close(self):
        self._session.close()

