"""Unit Tests for Whale & Smart-Money Intelligence Engine."""

from datetime import datetime, timezone
import pytest
from quantai.ingestion.schema import BlockchainTxData
from quantai.intelligence.whale.engine import WhaleIntelligenceEngine, WalletCategory


@pytest.fixture
def whale_engine():
    return WhaleIntelligenceEngine()


def test_whale_threshold_filtering(whale_engine):
    # Small transfer ($10,000) should be ignored
    small_tx = BlockchainTxData(
        source="test",
        event_time=datetime.now(timezone.utc),
        symbol="BTC/USDT",
        data_type="tx",
        tx_hash="0xsmall123",
        blockchain="bitcoin",
        from_address="0xabc",
        to_address="0xdef",
        amount=0.15,
        usd_value=10_000.0,
    )
    sig = whale_engine.process_transaction(small_tx)
    assert sig is None


def test_exchange_inflow_classification(whale_engine):
    # Large $1.5M transfer to Binance exchange wallet
    large_inflow = BlockchainTxData(
        source="test",
        event_time=datetime.now(timezone.utc),
        symbol="BTC/USDT",
        data_type="tx",
        tx_hash="0xlarge123",
        blockchain="bitcoin",
        from_address="0xwhale_unknown_wallet",
        to_address="0x_binance_deposit_hot_wallet",
        amount=22.0,
        usd_value=1_500_000.0,
    )
    sig = whale_engine.process_transaction(large_inflow)
    assert sig is not None
    assert sig.event_type == "EXCHANGE_INFLOW"
    assert sig.signal_bias == "BEARISH"


def test_smart_money_score_calculation(whale_engine):
    score = whale_engine.compute_smart_money_score(
        win_rate=0.68,
        profit_factor=2.1,
        total_trades=40,
        max_drawdown=0.08,
        confidence=0.90,
    )
    assert 60.0 <= score <= 100.0

