"""Unit Tests for Paper Trading Auditor & Excel Exporter."""

import os
import openpyxl
import pytest
from quantai.research.paper_auditor import PaperTradingAuditor


def test_paper_auditor_simulation_and_excel(tmp_path):
    auditor = PaperTradingAuditor(initial_capital=100_000.0)
    sim_data = auditor.run_simulation(symbol="BTC/USDT", timeframe="5m", candles_count=60)

    assert sim_data["candles_evaluated"] > 0
    assert len(sim_data["decisions_log"]) > 0
    assert len(sim_data["agent_breakdown_log"]) > 0

    # Test Excel generation
    excel_path = os.path.join(tmp_path, "test_audit.xlsx")
    saved_file = auditor.generate_excel_workbook(sim_data, output_filepath=excel_path)

    assert os.path.exists(saved_file)
    wb = openpyxl.load_workbook(saved_file)
    assert "Executive Summary" in wb.sheetnames
    assert "Trade Execution Log" in wb.sheetnames
    assert "Decision Audit Log" in wb.sheetnames
    assert "Multi-Agent Deliberation" in wb.sheetnames

    # Verify decision rows are populated
    ws_dec = wb["Decision Audit Log"]
    assert ws_dec.max_row >= 2
    header = [c.value for c in ws_dec[1]]
    assert "Timestamp" in header
    assert "Validation Integrity" in header
