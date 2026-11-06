"""Quantitative & Statistical Financial Mathematics Library."""

from typing import Dict, Tuple
import numpy as np
from quantai.common import pd


class QuantAnalytics:
    """Institutional quantitative analytics for risk, volatility, and return distributions."""

    @staticmethod
    def rolling_zscore(series: pd.Series, window: int = 30) -> pd.Series:
        mean = series.rolling(window=window).mean()
        std = series.rolling(window=window).std()
        return (series - mean) / (std + 1e-10)

    @staticmethod
    def hurst_exponent(price_series: pd.Series, max_lag: int = 20) -> float:
        """
        Calculates Hurst Exponent (H):
        H < 0.5: Mean-reverting process
        H = 0.5: Geometric Brownian Motion (random walk)
        H > 0.5: Persistent trending process
        """
        if len(price_series) < max_lag * 2:
            return 0.5

        ts = np.asarray(price_series)
        lags = range(2, max_lag)
        tau = [np.std(np.subtract(ts[lag:], ts[:-lag])) for lag in lags]

        # Linear fit of log(tau) against log(lag)
        poly = np.polyfit(np.log(lags), np.log(tau), 1)
        return float(np.clip(poly[0], 0.0, 1.0))

    @staticmethod
    def ewma_volatility(returns: pd.Series, lambda_param: float = 0.94) -> pd.Series:
        """RiskMetrics EWMA Volatility estimator (instantaneous GARCH(1,1) proxy)."""
        squared = returns**2
        return np.sqrt(squared.ewm(alpha=(1 - lambda_param), adjust=False).mean())

    @staticmethod
    def value_at_risk(returns: pd.Series, confidence: float = 0.95) -> float:
        """Historical Value at Risk (VaR) at given confidence level."""
        if len(returns) == 0:
            return 0.0
        return float(abs(np.percentile(returns, (1 - confidence) * 100)))

    @staticmethod
    def conditional_var(returns: pd.Series, confidence: float = 0.95) -> float:
        """Expected Shortfall (CVaR) beyond VaR threshold."""
        var = QuantAnalytics.value_at_risk(returns, confidence)
        tail_losses = returns[returns <= -var]
        if len(tail_losses) == 0:
            return var
        return float(abs(tail_losses.mean()))

    @staticmethod
    def calculate_performance_metrics(
        trade_returns: pd.Series,
        annualization_factor: float = 365 * 288,  # 5m candles in a year
    ) -> Dict[str, float]:
        """Calculates institutional risk-adjusted return ratios."""
        if len(trade_returns) < 2:
            return {
                "sharpe_ratio": 0.0,
                "sortino_ratio": 0.0,
                "calmar_ratio": 0.0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "max_drawdown": 0.0,
            }

        mean_ret = trade_returns.mean()
        std_ret = trade_returns.std()
        downside_std = trade_returns[trade_returns < 0].std()

        sharpe = (mean_ret / (std_ret + 1e-10)) * np.sqrt(annualization_factor)
        sortino = (mean_ret / (downside_std + 1e-10)) * np.sqrt(annualization_factor)

        # Drawdown computation
        cum_ret = (1 + trade_returns).cumprod()
        running_max = cum_ret.cummax()
        drawdown = (cum_ret - running_max) / running_max
        max_dd = float(abs(drawdown.min())) if len(drawdown) > 0 else 0.0

        calmar = (mean_ret * annualization_factor) / (max_dd + 1e-10)

        wins = trade_returns[trade_returns > 0]
        losses = trade_returns[trade_returns < 0].abs()
        win_rate = len(wins) / len(trade_returns)
        profit_factor = (wins.sum() / (losses.sum() + 1e-10)) if len(losses) > 0 else 999.0

        return {
            "sharpe_ratio": round(float(sharpe), 2),
            "sortino_ratio": round(float(sortino), 2),
            "calmar_ratio": round(float(calmar), 2),
            "win_rate": round(float(win_rate), 4),
            "profit_factor": round(float(profit_factor), 2),
            "max_drawdown": round(float(max_dd), 4),
        }
