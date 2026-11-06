"""Unit Tests for Continuous Live Observer & Excel Sync."""

import os
import openpyxl
import pytest
from quantai.execution.live_observer import LiveMarketObserver


def test_live_observer_cycle_and_excel_generation(tmp_path):
    excel_path = str(tmp_path / "test_live_trades.xlsx")
    observer = LiveMarketObserver(excel_path=excel_path, poll_interval_seconds=1.0)

    # Run scan on BTC/USDT
    observer.scan_and_analyze("BTC/USDT")

    assert os.path.exists(excel_path)
    wb = openpyxl.load_workbook(excel_path)
    assert "Live Performance Summary" in wb.sheetnames
    assert "Marked Trades Ledger" in wb.sheetnames
    assert "Real-Time Decisions Log" in wb.sheetnames

    # Verify decision is logged
    ws_dec = wb["Real-Time Decisions Log"]
    assert ws_dec.max_row >= 2
    row2 = [c.value for c in ws_dec[2]]
    assert "BTC/USDT" in row2


def test_open_trade_tp_sl_resolution(tmp_path):
    excel_path = str(tmp_path / "test_trade_resolution.xlsx")
    observer = LiveMarketObserver(excel_path=excel_path)

    # Manually mark a test BUY trade
    observer.active_trades["BTC/USDT"] = {
        "trade_id": "TEST_001",
        "pair": "BTC/USDT",
        "status": "OPEN",
        "side": "BUY",
        "entry_time": "2026-01-01 00:00:00 UTC",
        "exit_time": "IN_PROGRESS",
        "entry_price": 60000.0,
        "current_price": 60000.0,
        "allocated_usd": 1000.0,
        "amount": 0.01666,
        "take_profit": 62000.0,
        "stop_loss": 59000.0,
        "risk_reward_ratio": 2.0,
        "fee_entry_usd": 0.75,
        "exit_reason": "MONITORING",
        "thesis_confirmed": "PENDING",
        "strategy_rationale": "Unit test thesis",
    }

    # Simulate price advancing above take-profit ($62,500)
    resolved = observer.evaluate_open_trades("BTC/USDT", current_price=62500.0)
    assert len(resolved) == 1
    t = resolved[0]
    assert t["status"] == "CLOSED_WIN"
    assert t["thesis_confirmed"] == "YES"
    assert t["realized_pnl_usd"] > 0
    assert "BTC/USDT" not in observer.active_trades
    assert len(observer.completed_trades) == 1


def test_forward_replay_execution(tmp_path):
    excel_path = str(tmp_path / "test_forward_replay.xlsx")
    observer = LiveMarketObserver(excel_path=excel_path)

    # Run replay across 60 bars
    summary = observer.run_forward_replay(pair="BTC/USDT", total_bars=60)
    assert os.path.exists(excel_path)
    assert summary["total_bars_replayed"] == 25
    assert "excel_report" in summary
    assert "win_rate_pct" in summary

    wb = openpyxl.load_workbook(excel_path)
    assert "Live Performance Summary" in wb.sheetnames
    assert "Real-Time Decisions Log" in wb.sheetnames
    ws_dec = wb["Real-Time Decisions Log"]
    assert ws_dec.max_row > 10
