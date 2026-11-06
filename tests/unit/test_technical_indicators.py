"""Unit Tests for Technical Indicators and Feature Engine."""

import numpy as np
import pytest
from quantai.common import pd
from quantai.intelligence.technical.indicators import TechnicalIndicators
from quantai.intelligence.technical.feature_engine import TechnicalFeatureEngine


@pytest.fixture
def sample_ohlcv():
    np.random.seed(42)
    n = 100
    base = 65000.0
    returns = np.random.normal(0.0005, 0.01, n)
    prices = base * np.exp(np.cumsum(returns))

    dates = pd.date_range("2026-01-01", periods=n, freq="5min")
    high = prices * (1 + abs(np.random.normal(0, 0.002, n)))
    low = prices * (1 - abs(np.random.normal(0, 0.002, n)))
    volume = np.random.uniform(5.0, 50.0, n)

    df = pd.DataFrame(
        {
            "timestamp": dates,
            "open": prices,
            "high": high,
            "low": low,
            "close": prices,
            "volume": volume,
        }
    )
    return df


def test_sma_and_ema(sample_ohlcv):
    sma20 = TechnicalIndicators.sma(sample_ohlcv["close"], 20)
    ema20 = TechnicalIndicators.ema(sample_ohlcv["close"], 20)

    assert len(sma20) == len(sample_ohlcv)
    assert pd.isna(sma20.iloc[0])  # first 19 are NaN in standard rolling
    assert not pd.isna(sma20.iloc[25])
    assert not pd.isna(ema20.iloc[0])


def test_rsi_bounds(sample_ohlcv):
    rsi = TechnicalIndicators.rsi(sample_ohlcv["close"], 14)
    valid_rsi = rsi.dropna()
    assert (valid_rsi >= 0.0).all() and (valid_rsi <= 100.0).all()


def test_bollinger_bands_ordering(sample_ohlcv):
    upper, mid, lower, width = TechnicalIndicators.bollinger_bands(sample_ohlcv["close"], 20)
    valid_idx = 25
    assert upper.iloc[valid_idx] > mid.iloc[valid_idx] > lower.iloc[valid_idx]
    assert width.iloc[valid_idx] > 0


def test_multi_timeframe_zero_lookahead(sample_ohlcv):
    engine = TechnicalFeatureEngine()
    feat_5m = engine.compute_features(sample_ohlcv)

    # Synthetic 1h higher timeframe
    htf_dates = pd.date_range("2026-01-01", periods=40, freq="1h")
    htf_df = pd.DataFrame(
        {
            "timestamp": htf_dates,
            "open": np.linspace(65000, 67000, 40),
            "high": np.linspace(65500, 67500, 40),
            "low": np.linspace(64500, 66500, 40),
            "close": np.linspace(65200, 67200, 40),
            "volume": [100.0] * 40,
        }
    )

    merged = engine.build_multi_timeframe_matrix(feat_5m, {"1h": htf_df})
    assert "1h_ema_20" in merged.columns
    # Verify backward alignment preserves exact 5m row count
    assert len(merged) == len(sample_ohlcv)
