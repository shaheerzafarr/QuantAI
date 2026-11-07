import pytest
from unittest.mock import MagicMock, patch
from quantai.execution.binance_live import BinanceLiveFuturesExecutor
from quantai.execution.live_observer import LiveMarketObserver


def test_symbol_normalization():
    executor = BinanceLiveFuturesExecutor(api_key="mock_key", api_secret="mock_sec")
    assert executor._normalize_symbol("BTC/USDT") == "BTC/USDT:USDT"
    assert executor._normalize_symbol("ETHUSDT") == "ETH/USDT:USDT"
    assert executor._normalize_symbol("SOL/USDT:USDT") == "SOL/USDT:USDT"


def test_calculate_order_quantity_fallback():
    executor = BinanceLiveFuturesExecutor(api_key="mock_key", api_secret="mock_sec")
    # Notional $25 at price $100 -> 0.25 assets
    qty = executor.calculate_order_quantity("SOL/USDT", notional_usd=25.0, current_price=100.0)
    assert qty == 0.25


@patch("requests.get")
def test_check_api_permissions(mock_get):
    executor = BinanceLiveFuturesExecutor(api_key="mock_key", api_secret="mock_sec")
    
    # Simulate permissions response
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "enableReading": True,
        "enableFutures": True,
        "enableSpotAndMarginTrading": False,
        "ipRestrict": False,
    }
    mock_get.return_value = mock_resp

    perms = executor.check_api_permissions()
    assert perms["authenticated"] is True
    assert perms["can_read"] is True
    assert perms["can_trade_futures"] is True


def test_execute_live_entry_without_futures_permission():
    executor = BinanceLiveFuturesExecutor(api_key="mock_key", api_secret="mock_sec")
    with patch.object(executor, "check_api_permissions", return_value={"can_trade_futures": False, "reason": "No Futures"}):
        res = executor.execute_live_entry(
            symbol="SOL/USDT",
            side="BUY",
            notional_usd=25.0,
            current_price=150.0,
        )
        assert res["success"] is False
        assert "Binance API permission check failed" in res["error"]


def test_execute_live_entry_success():
    executor = BinanceLiveFuturesExecutor(api_key="mock_key", api_secret="mock_sec")
    with patch.object(executor, "check_api_permissions", return_value={"can_trade_futures": True}):
        with patch.object(executor, "setup_symbol_margin_and_leverage", return_value=True):
            executor.exchange = MagicMock()
            executor.exchange.create_market_order.return_value = {
                "id": "12345678",
                "filled": 0.15,
                "average": 150.25,
            }
            res = executor.execute_live_entry(
                symbol="SOL/USDT",
                side="BUY",
                notional_usd=25.0,
                current_price=150.0,
            )
            assert res["success"] is True
            assert res["order_id"] == "12345678"
            assert res["filled_qty"] == 0.15
            assert res["avg_price"] == 150.25


def test_execute_live_close_success():
    executor = BinanceLiveFuturesExecutor(api_key="mock_key", api_secret="mock_sec")
    executor.exchange = MagicMock()
    executor.exchange.create_order.return_value = {
        "id": "87654321",
        "average": 155.50,
    }
    res = executor.execute_live_close(symbol="SOL/USDT", side="LONG", amount=0.15)
    assert res["success"] is True
    assert res["order_id"] == "87654321"
    assert res["exit_price"] == 155.50
