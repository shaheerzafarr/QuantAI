"""Unit Tests for Binance Real-Time WebSocket Streaming Client."""

import pytest
from quantai.ingestion.websocket import BinanceWebSocketClient


def test_websocket_client_initialization():
    client = BinanceWebSocketClient(pairs=["BTC/USDT", "ETH/USDT"], timeframe="5m")
    assert client.pairs == ["BTC/USDT", "ETH/USDT"]
    assert client.timeframe == "5m"
    assert not client.running

    url = client._build_combined_stream_url()
    assert "btcusdt@kline_5m" in url
    assert "ethusdt@kline_5m" in url
    assert "btcusdt@ticker" in url


def test_symbol_formatting():
    client = BinanceWebSocketClient()
    assert client._format_symbol("BTCUSDT") == "BTC/USDT"
    assert client._format_symbol("ETHUSDT") == "ETH/USDT"
    assert client._format_symbol("SOLUSDT") == "SOL/USDT"


def test_kline_stream_message_handling():
    received_candles = []

    def on_candle(candle, is_closed):
        received_candles.append((candle, is_closed))

    client = BinanceWebSocketClient(on_candle_update=on_candle)

    # Simulated Binance payload
    sample_payload = {
        "stream": "btcusdt@kline_5m",
        "data": {
            "s": "BTCUSDT",
            "k": {
                "t": 1700000000000,
                "o": "76000.0",
                "h": "76500.0",
                "l": "75800.0",
                "c": "76300.0",
                "v": "125.5",
                "n": 500,
                "i": "5m",
                "x": True,  # closed bar
            },
        },
    }

    client._handle_stream_message(sample_payload)

    assert len(received_candles) == 1
    candle, is_closed = received_candles[0]
    assert candle.symbol == "BTC/USDT"
    assert candle.close == 76300.0
    assert candle.high == 76500.0
    assert is_closed is True
    assert client.latest_prices["BTC/USDT"] == 76300.0


def test_ticker_stream_message_handling():
    ticks = []

    def on_tick(pair, price):
        ticks.append((pair, price))

    client = BinanceWebSocketClient(on_price_tick=on_tick)

    sample_ticker = {
        "stream": "ethusdt@ticker",
        "data": {
            "s": "ETHUSDT",
            "c": "2245.50",
        },
    }

    client._handle_stream_message(sample_ticker)

    assert len(ticks) == 1
    assert ticks[0] == ("ETH/USDT", 2245.50)
    assert client.latest_prices["ETH/USDT"] == 2245.50
