"""Unit Tests for Multi-Regime Forward Stress Testing Engine."""

import os
import openpyxl
import pytest
from quantai.research.stress_tester import StressTestingEngine


def test_stress_scenario_dataset_generation():
    engine = StressTestingEngine()
    df = engine.generate_stress_scenario_dataset(base_price=60_000.0, bars_per_regime=30)
    assert len(df) == 120
    assert "close" in df.columns
    assert "volume" in df.columns
    # Verify flash crash regime has negative price impact
    p_regime1 = df.iloc[29]["close"]
    p_crash = df.iloc[89]["close"]
    # Check volume spike during panic
    max_vol = df["volume"].max()
    assert max_vol > 400.0


def test_stress_simulation_run(tmp_path):
    excel_path = str(tmp_path / "test_stress_audit.xlsx")
    engine = StressTestingEngine(excel_path=excel_path, initial_capital=100_000.0)

    summary = engine.run_stress_simulation(pair="BTC/USDT", bars_per_regime=30)
    assert os.path.exists(excel_path)
    assert "total_bars_evaluated" in summary
    assert "win_rate_pct" in summary
    assert "circuit_breaker_triggered" in summary

    wb = openpyxl.load_workbook(excel_path)
    assert "Live Performance Summary" in wb.sheetnames
    assert "Marked Trades Ledger" in wb.sheetnames
    assert "Real-Time Decisions Log" in wb.sheetnames

