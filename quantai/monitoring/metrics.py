"""Prometheus & Operational Telemetry Metrics Exporter for QuantAI."""

from typing import Dict, Any
from quantai.risk.guardian import IndependentRiskGuardian
from quantai.execution.paper_engine import PaperExecutionEngine


class MetricsCollector:
    """Generates standard Prometheus-compatible telemetry text strings."""

    @staticmethod
    def format_prometheus_metrics(
        risk_guardian: IndependentRiskGuardian,
        execution_engine: PaperExecutionEngine,
    ) -> str:
        lines = [
            "# HELP quantai_portfolio_balance_usd Total portfolio balance in USD",
            "# TYPE quantai_portfolio_balance_usd gauge",
            f"quantai_portfolio_balance_usd {risk_guardian.total_capital:.2f}",
            "",
            "# HELP quantai_available_balance_usd Available unallocated capital in USD",
            "# TYPE quantai_available_balance_usd gauge",
            f"quantai_available_balance_usd {risk_guardian.available_capital:.2f}",
            "",
            "# HELP quantai_active_exposure_usd Active open position exposure in USD",
            "# TYPE quantai_active_exposure_usd gauge",
            f"quantai_active_exposure_usd {risk_guardian.active_exposure_usd:.2f}",
            "",
            "# HELP quantai_daily_drawdown_ratio Daily drawdown percentage ratio (0.0 to 1.0)",
            "# TYPE quantai_daily_drawdown_ratio gauge",
            f"quantai_daily_drawdown_ratio {((risk_guardian.daily_start_capital - risk_guardian.total_capital) / risk_guardian.daily_start_capital):.4f}",
            "",
            "# HELP quantai_emergency_halt_flag Emergency circuit breaker state (0 = Normal, 1 = Halted)",
            "# TYPE quantai_emergency_halt_flag gauge",
            f"quantai_emergency_halt_flag {1 if risk_guardian.emergency_halt else 0}",
            "",
            "# HELP quantai_open_orders_count Number of open active paper positions",
            "# TYPE quantai_open_orders_count gauge",
            f"quantai_open_orders_count {len(execution_engine.open_orders)}",
            "",
        ]
        return "\n".join(lines) + "\n"

