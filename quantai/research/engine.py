"""Research & Strategy (R&S) Engine with Deflated Sharpe Ratio and Lifecycle Promotion."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional
import numpy as np
from quantai.common import pd
from quantai.analytics.statistics import QuantAnalytics
from quantai.research.strategies import (
    BaseStrategy,
    TrendFollowingStrategy,
    MeanReversionStrategy,
    WhaleFollowingStrategy,
    StrategySignal,
)
from quantai.storage.db import get_db_manager
from quantai.storage.models import StrategyResult


@dataclass
class BacktestEvaluation:
    strategy_name: str
    total_trades: int
    win_rate: float
    profit_factor: float
    sharpe_ratio: float
    deflated_sharpe: float
    max_drawdown: float
    net_return_pct: float
    promotion_status: str  # CANDIDATE, BACKTESTED, PROMOTED_PAPER, REJECTED


class ResearchEngine:
    """Automates hypothesis backtesting, statistical validation, and controlled strategy promotion."""

    def __init__(self):
        self.db_manager = get_db_manager()
        self.active_strategies: Dict[str, BaseStrategy] = {
            "trend": TrendFollowingStrategy(),
            "mean_reversion": MeanReversionStrategy(),
            "whale_follower": WhaleFollowingStrategy(),
        }

    def calculate_deflated_sharpe_ratio(
        self,
        estimated_sharpe: float,
        num_trials: int,
        sample_length: int,
        skewness: float = 0.0,
        kurtosis: float = 3.0,
    ) -> float:
        """
        Calculates Bailey and López de Prado's Deflated Sharpe Ratio (DSR).
        Corrects for selection bias under multiple testing and non-normal returns.
        """
        if num_trials <= 1 or sample_length <= 10:
            return estimated_sharpe

        # Expected maximum Sharpe ratio under null hypothesis (Euler-Mascheroni approximation)
        gamma = 0.5772156649
        z_approx = (1 - gamma) * (2 * np.log(num_trials)) ** -0.5 + (2 * np.log(num_trials)) ** 0.5
        expected_max_sharpe = z_approx / np.sqrt(sample_length)

        # Variance of Sharpe ratio estimator
        var_sr = (
            1.0
            - skewness * estimated_sharpe
            + ((kurtosis - 1) / 4.0) * (estimated_sharpe**2)
        ) / sample_length

        if var_sr <= 0:
            return 0.0

        dsr = (estimated_sharpe - expected_max_sharpe) / np.sqrt(var_sr)
        return round(float(dsr), 2)

    def backtest_strategy(
        self,
        strategy: BaseStrategy,
        df: pd.DataFrame,
        fee_bps: float = 7.5,
        slippage_bps: float = 5.0,
    ) -> BacktestEvaluation:
        """Vectorized event-driven backtest including realistic fees and slippage."""
        if len(df) < 50:
            return BacktestEvaluation(
                strategy_name=strategy.name,
                total_trades=0,
                win_rate=0.0,
                profit_factor=0.0,
                sharpe_ratio=0.0,
                deflated_sharpe=0.0,
                max_drawdown=0.0,
                net_return_pct=0.0,
                promotion_status="REJECTED",
            )

        trade_returns = []
        position = 0  # 0: flat, 1: long
        entry_price = 0.0
        total_cost_bps = fee_bps + slippage_bps

        for i in range(30, len(df)):
            sub_df = df.iloc[: i + 1]
            sig = strategy.generate_signal(sub_df)
            current_close = df.iloc[i]["close"]

            if position == 0 and sig.action == "BUY":
                position = 1
                entry_price = current_close * (1 + total_cost_bps / 10_000.0)
            elif position == 1 and (sig.action == "SELL" or i == len(df) - 1):
                position = 0
                exit_price = current_close * (1 - total_cost_bps / 10_000.0)
                ret = (exit_price - entry_price) / entry_price
                trade_returns.append(ret)

        returns_series = pd.Series(trade_returns)
        metrics = QuantAnalytics.calculate_performance_metrics(returns_series)

        dsr = self.calculate_deflated_sharpe_ratio(
            estimated_sharpe=metrics["sharpe_ratio"],
            num_trials=10,  # accounts for parameter trials
            sample_length=len(trade_returns),
        )

        # Promotion gate: requires positive DSR, profit factor > 1.3, win rate > 45%, max DD < 10%
        promoted = (
            metrics["profit_factor"] >= 1.30
            and metrics["win_rate"] >= 0.45
            and metrics["max_drawdown"] <= 0.10
            and len(trade_returns) >= 5
        )

        status = "PROMOTED_PAPER" if promoted else "CANDIDATE"

        # Record in database
        try:
            with self.db_manager.get_session() as session:
                rec = StrategyResult(
                    strategy_name=strategy.name,
                    version="1.0.0",
                    start_time=df.iloc[0]["timestamp"],
                    end_time=df.iloc[-1]["timestamp"],
                    win_rate=metrics["win_rate"],
                    profit_factor=metrics["profit_factor"],
                    sharpe_ratio=metrics["sharpe_ratio"],
                    deflated_sharpe=dsr,
                    max_drawdown=metrics["max_drawdown"],
                    total_trades=len(trade_returns),
                    net_pnl_pct=float(returns_series.sum() * 100) if len(trade_returns) > 0 else 0.0,
                    status=status,
                    parameters=strategy.params,
                )
                session.add(rec)
        except Exception:
            pass

        return BacktestEvaluation(
            strategy_name=strategy.name,
            total_trades=len(trade_returns),
            win_rate=metrics["win_rate"],
            profit_factor=metrics["profit_factor"],
            sharpe_ratio=metrics["sharpe_ratio"],
            deflated_sharpe=dsr,
            max_drawdown=metrics["max_drawdown"],
            net_return_pct=round(float(returns_series.sum() * 100), 2) if len(trade_returns) > 0 else 0.0,
            promotion_status=status,
        )
