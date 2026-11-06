"""Unit Tests for Benchmark Evaluation Suite."""

import numpy as np
import pytest
from quantai.common import pd
from quantai.research.benchmarks import BenchmarkEvaluator


def test_benchmark_suite_execution():
    np.random.seed(42)
    n = 80
    dates = pd.date_range("2026-01-01", periods=n, freq="5min")
    prices = 65000.0 * np.exp(np.cumsum(np.random.normal(0.0002, 0.005, n)))
    df = pd.DataFrame(
        {
            "timestamp": dates,
            "open": prices,
            "high": prices * 1.002,
            "low": prices * 0.998,
            "close": prices,
            "volume": np.random.uniform(10.0, 50.0, n),
        }
    )

    evaluator = BenchmarkEvaluator()
    results = evaluator.run_all(df, symbol="BTC/USDT")

    assert len(results) == 7
    names = [r.strategy_name for r in results]
    assert "Buy & Hold BTC" in names
    assert "Simple EMA (20/50)" in names
    assert "RSI Mean Reversion (30/70)" in names
    assert "ML Calibrated Model Only" in names
    assert "Whale Tracking Only" in names
    assert "Full QuantAI Multi-Agent Engine" in names

    for r in results:
        assert isinstance(r.win_rate_pct, float)
        assert isinstance(r.net_pnl_pct, float)
        assert isinstance(r.sharpe_ratio, float)
