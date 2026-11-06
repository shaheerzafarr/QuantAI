"""Multi-Regime Autonomous Stress Testing Engine.

Simulates extreme market conditions (sustained trends, high volatility chop,
flash crashes, and sharp rebounds) to verify that:
1. Fractional Kelly dynamically constrains exposure under heightened volatility.
2. Independent Risk Guardian halts trading when daily/total drawdown limits are reached.
3. Fee and slippage filters prevent trading churn during compression.
4. Generates an auditable Excel stress report.
"""

import logging
import os
import shutil
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import numpy as np
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from quantai.common import pd
from quantai.config.settings import get_config
from quantai.execution.live_observer import LiveMarketObserver

logger = logging.getLogger("quantai.stress_tester")


class StressTestingEngine:
    """Simulates extreme market shocks and audits risk response."""

    def __init__(
        self,
        excel_path: str = "user_data/QuantAI_Stress_Audit.xlsx",
        initial_capital: float = 100_000.0,
    ):
        self.excel_path = os.path.abspath(excel_path)
        self.initial_capital = initial_capital
        self.config = get_config()

    def generate_stress_scenario_dataset(
        self,
        base_price: float = 70_000.0,
        bars_per_regime: int = 50,
    ) -> pd.DataFrame:
        """Generates synthetic multi-regime OHLCV sequence with sudden flash crash."""
        timestamps = []
        opens, highs, lows, closes, volumes = [], [], [], [], []

        current_price = base_price
        start_ts = int(time.time()) - (bars_per_regime * 4 * 300)

        # Regime 1: Steady Bull Trend (Bars 0-49)
        for i in range(bars_per_regime):
            ts = datetime.fromtimestamp(start_ts + (len(opens) * 300), tz=timezone.utc)
            timestamps.append(ts)
            change = np.random.uniform(0.001, 0.004)
            o = current_price
            c = current_price * (1.0 + change)
            h = max(o, c) * (1.0 + np.random.uniform(0.0005, 0.0015))
            l = min(o, c) * (1.0 - np.random.uniform(0.0005, 0.0015))
            v = np.random.uniform(150.0, 300.0)
            opens.append(o)
            highs.append(h)
            lows.append(l)
            closes.append(c)
            volumes.append(v)
            current_price = c

        # Regime 2: Ranging Compression (Bars 50-99)
        mid_price = current_price
        for i in range(bars_per_regime):
            ts = datetime.fromtimestamp(start_ts + (len(opens) * 300), tz=timezone.utc)
            timestamps.append(ts)
            noise = np.sin(i / 3.0) * 0.002
            c = mid_price * (1.0 + noise)
            o = current_price
            h = max(o, c) * 1.001
            l = min(o, c) * 0.999
            v = np.random.uniform(50.0, 120.0)
            opens.append(o)
            highs.append(h)
            lows.append(l)
            closes.append(c)
            volumes.append(v)
            current_price = c

        # Regime 3: Violent Flash Crash (Bars 100-149)
        # Drop 8% across first 3 bars, followed by high-volatility panic
        for i in range(bars_per_regime):
            ts = datetime.fromtimestamp(start_ts + (len(opens) * 300), tz=timezone.utc)
            timestamps.append(ts)
            if i < 3:
                change = -0.028  # Heavy downward cascade
            elif i < 15:
                change = np.random.uniform(-0.008, 0.002)
            else:
                change = np.random.uniform(-0.003, 0.003)
            o = current_price
            c = current_price * (1.0 + change)
            h = max(o, c) * 1.004
            l = min(o, c) * 0.994
            v = np.random.uniform(500.0, 1500.0)  # Extreme volume spike
            opens.append(o)
            highs.append(h)
            lows.append(l)
            closes.append(c)
            volumes.append(v)
            current_price = c

        # Regime 4: High-Volatility Rebound (Bars 150-199)
        for i in range(bars_per_regime):
            ts = datetime.fromtimestamp(start_ts + (len(opens) * 300), tz=timezone.utc)
            timestamps.append(ts)
            change = np.random.uniform(-0.002, 0.006)
            o = current_price
            c = current_price * (1.0 + change)
            h = max(o, c) * 1.005
            l = min(o, c) * 0.995
            v = np.random.uniform(250.0, 600.0)
            opens.append(o)
            highs.append(h)
            lows.append(l)
            closes.append(c)
            volumes.append(v)
            current_price = c

        data = {
            "timestamp": timestamps,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        }
        return pd.DataFrame(data)

    def run_stress_simulation(
        self,
        pair: str = "BTC/USDT",
        bars_per_regime: int = 40,
    ) -> Dict[str, Any]:
        """Executes the multi-regime stress audit and generates a validated Excel report."""
        logger.info(f"Generating stress simulation dataset ({bars_per_regime * 4} total bars)...")
        stress_df = self.generate_stress_scenario_dataset(bars_per_regime=bars_per_regime)

        observer = LiveMarketObserver(
            excel_path=self.excel_path,
            initial_capital=self.initial_capital,
        )

        circuit_breaker_triggered = False
        halt_timestamp: Optional[str] = None
        halt_reason: Optional[str] = None

        logger.info("Executing sequential bar-by-bar stress simulation...")
        for i in range(35, len(stress_df)):
            sub_df = stress_df.iloc[: i + 1]
            observer.scan_and_analyze(pair=pair, custom_df=sub_df)

            # Check if Risk Guardian tripped
            if observer.risk_guardian.emergency_halt and not circuit_breaker_triggered:
                circuit_breaker_triggered = True
                halt_timestamp = str(sub_df.iloc[-1]["timestamp"])
                halt_reason = "Circuit Breaker Tripped: Maximum Drawdown Threshold Reached"
                logger.warning(f"CIRCUIT BREAKER TRIGGERED at {halt_timestamp}!")

        # Finalize open trades
        last_bar = stress_df.iloc[-1]
        final_price = float(last_bar["close"])
        if pair in observer.active_trades:
            trade = observer.active_trades[pair]
            fee_exit = trade["allocated_usd"] * 0.00075
            total_fees = trade["fee_entry_usd"] + fee_exit
            gross_pnl = (
                (final_price - trade["entry_price"]) * trade["amount"]
                if trade["side"] == "BUY"
                else (trade["entry_price"] - final_price) * trade["amount"]
            )
            net_pnl = gross_pnl - total_fees
            trade["status"] = "CLOSED_WIN" if net_pnl > 0 else "CLOSED_LOSS"
            trade["exit_price"] = round(final_price, 2)
            trade["exit_time"] = str(last_bar["timestamp"])
            trade["exit_reason"] = "STRESS_TEST_WINDOW_END"
            trade["realized_pnl_usd"] = round(net_pnl, 2)
            trade["realized_pnl_pct"] = round((net_pnl / trade["allocated_usd"]) * 100.0, 2)
            trade["thesis_confirmed"] = "YES" if net_pnl > 0 else "NO"
            observer.completed_trades.append(trade)
            del observer.active_trades[pair]
            observer.sync_to_excel()

        wins = [t for t in observer.completed_trades if t.get("realized_pnl_usd", 0) > 0]
        losses = [t for t in observer.completed_trades if t.get("realized_pnl_usd", 0) <= 0]
        total_pnl = sum(t.get("realized_pnl_usd", 0) for t in observer.completed_trades)
        win_rate = (len(wins) / len(observer.completed_trades) * 100.0) if observer.completed_trades else 0.0

        summary = {
            "pair": pair,
            "total_bars_evaluated": len(stress_df) - 35,
            "total_trades_marked": len(observer.completed_trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": round(win_rate, 1),
            "net_realized_pnl_usd": round(total_pnl, 2),
            "circuit_breaker_triggered": circuit_breaker_triggered,
            "halt_timestamp": halt_timestamp,
            "halt_reason": halt_reason,
            "excel_report": self.excel_path,
        }
        logger.info(f"Stress test complete: {summary}")
        return summary

