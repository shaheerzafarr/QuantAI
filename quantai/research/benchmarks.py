"""Benchmark Evaluation Suite for QuantAI (Section 8 of Master Plan).

Evaluates the Full QuantAI Decision Engine against mandatory industry benchmarks:
1. Buy & Hold BTC
2. Buy & Hold ETH
3. Simple EMA Cross (20/50)
4. RSI Mean Reversion (30/70)
5. Machine Learning (Calibrated Model) Only
6. Whale Flow Tracking Only
7. Technical + Whale Hybrid
8. Full QuantAI Multi-Agent Decision Engine
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
import numpy as np
from quantai.common import pd
from quantai.analytics.statistics import QuantAnalytics
from quantai.intelligence.technical.feature_engine import TechnicalFeatureEngine
from quantai.ml.pipeline import QuantMLModel
from quantai.agents.swarm import MultiAgentSwarm
from quantai.decision.engine import DecisionFusionEngine
from quantai.risk.guardian import IndependentRiskGuardian


@dataclass
class BenchmarkMetric:
    strategy_name: str
    total_trades: int
    win_rate_pct: float
    net_pnl_pct: float
    profit_factor: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown_pct: float
    expectancy_bps: float
    avg_slippage_bps: float


class BenchmarkEvaluator:
    """Executes multi-strategy comparative benchmarking with transaction costs and slippage."""

    def __init__(
        self,
        fee_bps: float = 7.5,
        slippage_bps: float = 3.0,
        initial_capital: float = 100_000.0,
    ):
        self.fee_bps = fee_bps
        self.slippage_bps = slippage_bps
        self.total_cost_bps = (fee_bps * 2) + slippage_bps
        self.initial_capital = initial_capital
        self.feature_engine = TechnicalFeatureEngine()

    def run_all(self, df: pd.DataFrame, symbol: str = "BTC/USDT") -> List[BenchmarkMetric]:
        """Runs all 8 benchmarks on the provided market dataset."""
        feat_df = self.feature_engine.compute_features(df)
        results = [
            self._benchmark_buy_and_hold(feat_df, f"Buy & Hold {symbol.split('/')[0]}"),
            self._benchmark_ema_cross(feat_df),
            self._benchmark_rsi(feat_df),
            self._benchmark_ml_only(feat_df, symbol),
            self._benchmark_whale_only(feat_df),
            self._benchmark_tech_whale_hybrid(feat_df),
            self._benchmark_full_quantai(feat_df, symbol),
        ]
        return results

    def _simulate_trades(
        self,
        df: pd.DataFrame,
        buy_signals: np.ndarray,
        sell_signals: np.ndarray,
        name: str,
    ) -> BenchmarkMetric:
        """Simulates trading lifecycle accounting for entry/exit execution friction."""
        trade_returns = []
        in_pos = False
        entry_price = 0.0

        close_prices = df["close"].values if hasattr(df["close"], "values") else np.asarray(df["close"])
        n = len(close_prices)

        for i in range(n):
            p = close_prices[i]
            if not in_pos and buy_signals[i]:
                in_pos = True
                entry_price = p * (1.0 + self.total_cost_bps / 10_000.0)
            elif in_pos and (sell_signals[i] or i == n - 1):
                in_pos = False
                exit_price = p * (1.0 - self.total_cost_bps / 10_000.0)
                ret = (exit_price - entry_price) / entry_price
                trade_returns.append(ret)

        ret_series = pd.Series(trade_returns)
        stats = QuantAnalytics.calculate_performance_metrics(ret_series)
        cum_ret = float(ret_series.sum() * 100) if len(trade_returns) > 0 else 0.0
        exp_bps = (float(ret_series.mean()) * 10_000) if len(trade_returns) > 0 else 0.0

        return BenchmarkMetric(
            strategy_name=name,
            total_trades=len(trade_returns),
            win_rate_pct=round(stats["win_rate"] * 100, 2),
            net_pnl_pct=round(cum_ret, 2),
            profit_factor=stats["profit_factor"],
            sharpe_ratio=stats["sharpe_ratio"],
            sortino_ratio=stats["sortino_ratio"],
            calmar_ratio=stats["calmar_ratio"],
            max_drawdown_pct=round(stats["max_drawdown"] * 100, 2),
            expectancy_bps=round(exp_bps, 1),
            avg_slippage_bps=self.slippage_bps,
        )

    def _benchmark_buy_and_hold(self, df: pd.DataFrame, name: str) -> BenchmarkMetric:
        """Buy at candle 0 and hold through final candle."""
        n = len(df)
        buys = np.zeros(n, dtype=bool)
        sells = np.zeros(n, dtype=bool)
        if n > 0:
            buys[0] = True
            sells[-1] = True
        return self._simulate_trades(df, buys, sells, name)

    def _benchmark_ema_cross(self, df: pd.DataFrame) -> BenchmarkMetric:
        """EMA 20 crossing over EMA 50."""
        n = len(df)
        buys = np.zeros(n, dtype=bool)
        sells = np.zeros(n, dtype=bool)

        ema20 = df["ema_20"].values
        ema50 = df["ema_50"].values

        for i in range(1, n):
            if ema20[i] > ema50[i] and ema20[i - 1] <= ema50[i - 1]:
                buys[i] = True
            elif ema20[i] < ema50[i] and ema20[i - 1] >= ema50[i - 1]:
                sells[i] = True

        return self._simulate_trades(df, buys, sells, "Simple EMA (20/50)")

    def _benchmark_rsi(self, df: pd.DataFrame) -> BenchmarkMetric:
        """RSI oversold (< 30) entry and overbought (> 70) exit."""
        n = len(df)
        buys = np.zeros(n, dtype=bool)
        sells = np.zeros(n, dtype=bool)
        rsi = df["rsi_14"].values

        for i in range(n):
            if rsi[i] < 30.0:
                buys[i] = True
            elif rsi[i] > 70.0:
                sells[i] = True

        return self._simulate_trades(df, buys, sells, "RSI Mean Reversion (30/70)")

    def _benchmark_ml_only(self, df: pd.DataFrame, symbol: str) -> BenchmarkMetric:
        """Pure Machine Learning (calibrated probability > 62%)."""
        n = len(df)
        buys = np.zeros(n, dtype=bool)
        sells = np.zeros(n, dtype=bool)

        model = QuantMLModel(model_version="bench_ml")
        X, y = model.prepare_dataset(df, forward_horizon=3, return_threshold=0.002)
        if len(X) > 20:
            model.fit(X, y)
            for i in range(len(X)):
                pred = model.predict_latest(X.iloc[i], symbol)
                if pred.target_class == "BUY":
                    buys[i] = True
                elif pred.target_class == "SELL":
                    sells[i] = True

        return self._simulate_trades(df, buys, sells, "ML Calibrated Model Only")

    def _benchmark_whale_only(self, df: pd.DataFrame) -> BenchmarkMetric:
        """Whale accumulation proxy based on volume spikes and price support."""
        n = len(df)
        buys = np.zeros(n, dtype=bool)
        sells = np.zeros(n, dtype=bool)
        vol = df["volume"].values
        mean_vol = np.mean(vol) if n > 0 else 1.0

        for i in range(n):
            # Volume 2.5x above average with positive close
            if vol[i] > mean_vol * 2.2 and df["close"].values[i] > df["open"].values[i]:
                buys[i] = True
            elif vol[i] > mean_vol * 2.2 and df["close"].values[i] < df["open"].values[i]:
                sells[i] = True

        return self._simulate_trades(df, buys, sells, "Whale Tracking Only")

    def _benchmark_tech_whale_hybrid(self, df: pd.DataFrame) -> BenchmarkMetric:
        """Technical trend + Whale volume confirmation."""
        n = len(df)
        buys = np.zeros(n, dtype=bool)
        sells = np.zeros(n, dtype=bool)
        ema20 = df["ema_20"].values
        ema50 = df["ema_50"].values
        vol = df["volume"].values
        mean_vol = np.mean(vol) if n > 0 else 1.0

        for i in range(n):
            if ema20[i] > ema50[i] and vol[i] > mean_vol * 1.5:
                buys[i] = True
            elif ema20[i] < ema50[i]:
                sells[i] = True

        return self._simulate_trades(df, buys, sells, "Technical + Whale Hybrid")

    def _benchmark_full_quantai(self, df: pd.DataFrame, symbol: str) -> BenchmarkMetric:
        """Full QuantAI Engine: 12-Agent Swarm, ML, Fusion, and Risk Guardian."""
        n = len(df)
        buys = np.zeros(n, dtype=bool)
        sells = np.zeros(n, dtype=bool)

        swarm = MultiAgentSwarm()
        fusion = DecisionFusionEngine(min_confidence=0.60, min_expected_edge_bps=10.0)
        risk = IndependentRiskGuardian(initial_capital_usd=self.initial_capital)

        # Sample at regular intervals to simulate realistic decision cadence
        step = max(1, n // 25)
        for i in range(30, n, step):
            sub_df = df.iloc[: i + 1]
            p = float(df["close"].values[i])
            ctx = {
                "symbol": symbol,
                "features_df": sub_df,
                "hurst_exponent": 0.58,
                "price_zscore": 0.5,
                "spread": 0.01,
                "estimated_slippage_bps": self.slippage_bps,
            }
            reports = swarm.run_swarm(ctx)
            dec = fusion.fuse_signals(symbol, reports, estimated_slippage_bps=self.slippage_bps)
            verdict = risk.evaluate_decision(dec, p)

            if verdict.approved:
                if verdict.action == "BUY":
                    buys[i] = True
                elif verdict.action == "SELL":
                    sells[i] = True

        return self._simulate_trades(df, buys, sells, "Full QuantAI Multi-Agent Engine")
