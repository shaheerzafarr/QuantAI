"""Quantitative Trading Strategy Library."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional
from quantai.common import pd


@dataclass
class StrategySignal:
    strategy_name: str
    symbol: str
    action: str  # BUY, SELL, HOLD
    strength: float  # 0.0 to 1.0
    rationale: str
    params: Dict[str, float]


class BaseStrategy(ABC):
    def __init__(self, name: str, params: Optional[Dict[str, float]] = None):
        self.name = name
        self.params = params or {}

    @abstractmethod
    def generate_signal(self, df: pd.DataFrame, symbol: str = "BTC/USDT") -> StrategySignal:
        pass


class TrendFollowingStrategy(BaseStrategy):
    """Exploits sustained momentum across moving average alignments and Supertrend."""

    def __init__(self, ema_fast: int = 20, ema_slow: int = 50):
        super().__init__(
            name="TrendFollowing_EMA",
            params={"ema_fast": float(ema_fast), "ema_slow": float(ema_slow)},
        )

    def generate_signal(self, df: pd.DataFrame, symbol: str = "BTC/USDT") -> StrategySignal:
        if len(df) < 50:
            return StrategySignal(self.name, symbol, "HOLD", 0.0, "Insufficient data", self.params)

        row = df.iloc[-1]
        prev_row = df.iloc[-2]

        close = row["close"]
        ema_fast = row.get("ema_20", close)
        ema_slow = row.get("ema_50", close)
        rsi = row.get("rsi_14", 50.0)

        # Bullish golden cross + RSI confirmation (> 50 and < 70)
        if ema_fast > ema_slow and prev_row.get("ema_20", 0) <= prev_row.get("ema_50", 0) and 50 < rsi < 70:
            return StrategySignal(
                self.name, symbol, "BUY", 0.85, "EMA 20/50 Golden Cross with bullish RSI momentum", self.params
            )
        # Bearish death cross
        elif ema_fast < ema_slow and prev_row.get("ema_20", 0) >= prev_row.get("ema_50", 0):
            return StrategySignal(
                self.name, symbol, "SELL", 0.85, "EMA 20/50 Death Cross downward breakout", self.params
            )

        return StrategySignal(self.name, symbol, "HOLD", 0.0, "Trend conditions neutral", self.params)


class MeanReversionStrategy(BaseStrategy):
    """Capitalizes on extreme price extensions beyond statistical Bollinger Bands."""

    def __init__(self, rsi_oversold: float = 30.0, rsi_overbought: float = 70.0):
        super().__init__(
            name="MeanReversion_BB",
            params={"rsi_oversold": rsi_oversold, "rsi_overbought": rsi_overbought},
        )

    def generate_signal(self, df: pd.DataFrame, symbol: str = "BTC/USDT") -> StrategySignal:
        if len(df) < 30:
            return StrategySignal(self.name, symbol, "HOLD", 0.0, "Insufficient data", self.params)

        row = df.iloc[-1]
        close = row["close"]
        bb_lower = row.get("bb_lower", close * 0.98)
        bb_upper = row.get("bb_upper", close * 1.02)
        rsi = row.get("rsi_14", 50.0)

        # Puncture below lower Bollinger Band with oversold RSI
        if close < bb_lower and rsi < self.params["rsi_oversold"]:
            return StrategySignal(
                self.name, symbol, "BUY", 0.80, f"Lower BB puncture ({close:.2f} < {bb_lower:.2f}) with RSI {rsi:.1f}", self.params
            )
        elif close > bb_upper and rsi > self.params["rsi_overbought"]:
            return StrategySignal(
                self.name, symbol, "SELL", 0.80, f"Upper BB puncture ({close:.2f} > {bb_upper:.2f}) with RSI {rsi:.1f}", self.params
            )

        return StrategySignal(self.name, symbol, "HOLD", 0.0, "Within normal volatility bands", self.params)


class WhaleFollowingStrategy(BaseStrategy):
    """Combines verified whale exchange outflows and accumulation with local technical confirmation."""

    def __init__(self, min_whale_score: float = 70.0):
        super().__init__(
            name="WhaleAccumulation_Follower",
            params={"min_whale_score": min_whale_score},
        )

    def evaluate_whale_signal(
        self, whale_signal_bias: str, whale_score: float, symbol: str = "BTC/USDT"
    ) -> StrategySignal:
        if whale_score < self.params["min_whale_score"]:
            return StrategySignal(self.name, symbol, "HOLD", 0.0, "Whale score below threshold", self.params)

        if whale_signal_bias == "BULLISH":
            return StrategySignal(
                self.name,
                symbol,
                "BUY",
                0.90,
                f"High-conviction whale accumulation (score: {whale_score})",
                self.params,
            )
        elif whale_signal_bias == "BEARISH":
            return StrategySignal(
                self.name,
                symbol,
                "SELL",
                0.90,
                f"Significant exchange inflow whale distribution (score: {whale_score})",
                self.params,
            )

        return StrategySignal(self.name, symbol, "HOLD", 0.0, "Neutral whale activity", self.params)

    def generate_signal(self, df: pd.DataFrame, symbol: str = "BTC/USDT") -> StrategySignal:
        return StrategySignal(self.name, symbol, "HOLD", 0.0, "Awaiting whale transaction trigger", self.params)
