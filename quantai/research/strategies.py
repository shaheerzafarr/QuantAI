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

        close = float(row["close"])
        ema_fast = float(row.get("ema_20", close))
        ema_slow = float(row.get("ema_50", close))
        rsi = float(row.get("rsi_14", 50.0))

        prev_ema_fast = float(prev_row.get("ema_20", ema_fast))
        prev_ema_slow = float(prev_row.get("ema_50", ema_slow))
        prev_close = float(prev_row.get("close", close))

        # 1. Bullish golden cross + RSI confirmation (> 50 and < 70)
        if ema_fast > ema_slow and prev_ema_fast <= prev_ema_slow and 50 < rsi < 70:
            return StrategySignal(
                self.name, symbol, "BUY", 0.85, "EMA 20/50 Golden Cross with bullish RSI momentum", self.params
            )
        # 2. Sustained bullish trend alignment
        elif close > ema_fast > ema_slow and 50.0 <= rsi <= 68.0 and close >= prev_close:
            return StrategySignal(
                self.name, symbol, "BUY", 0.75, f"Bullish trend continuation (Price > EMA20 > EMA50, RSI {rsi:.1f})", self.params
            )
        # 3. Bearish death cross
        elif ema_fast < ema_slow and prev_ema_fast >= prev_ema_slow:
            return StrategySignal(
                self.name, symbol, "SELL", 0.85, "EMA 20/50 Death Cross downward breakout", self.params
            )
        # 4. Sustained bearish trend alignment
        elif close < ema_fast < ema_slow and 32.0 <= rsi <= 50.0 and close <= prev_close:
            return StrategySignal(
                self.name, symbol, "SELL", 0.75, f"Bearish trend continuation (Price < EMA20 < EMA50, RSI {rsi:.1f})", self.params
            )

        return StrategySignal(self.name, symbol, "HOLD", 0.0, "Trend conditions neutral", self.params)


class MeanReversionStrategy(BaseStrategy):
    """Capitalizes on extreme price extensions beyond statistical Bollinger Bands."""

    def __init__(self, rsi_oversold: float = 35.0, rsi_overbought: float = 65.0):
        super().__init__(
            name="MeanReversion_BB",
            params={"rsi_oversold": rsi_oversold, "rsi_overbought": rsi_overbought},
        )

    def generate_signal(self, df: pd.DataFrame, symbol: str = "BTC/USDT") -> StrategySignal:
        if len(df) < 30:
            return StrategySignal(self.name, symbol, "HOLD", 0.0, "Insufficient data", self.params)

        row = df.iloc[-1]
        close = float(row["close"])
        bb_lower = float(row.get("bb_lower", close * 0.98))
        bb_upper = float(row.get("bb_upper", close * 1.02))
        rsi = float(row.get("rsi_14", 50.0))

        # Puncture below lower Bollinger Band with oversold RSI
        if close <= bb_lower * 1.002 and rsi <= self.params["rsi_oversold"]:
            return StrategySignal(
                self.name, symbol, "BUY", 0.80, f"Lower BB extension ({close:.2f} <= {bb_lower:.2f}) with RSI {rsi:.1f}", self.params
            )
        elif close >= bb_upper * 0.998 and rsi >= self.params["rsi_overbought"]:
            return StrategySignal(
                self.name, symbol, "SELL", 0.80, f"Upper BB extension ({close:.2f} >= {bb_upper:.2f}) with RSI {rsi:.1f}", self.params
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


class BreakoutMomentumStrategy(BaseStrategy):
    """Detects multi-period local highs/lows breakout supported by volume expansion."""

    def __init__(self, lookback_bars: int = 20):
        super().__init__(
            name="BreakoutMomentum_Vol",
            params={"lookback_bars": float(lookback_bars)},
        )

    def generate_signal(self, df: pd.DataFrame, symbol: str = "BTC/USDT") -> StrategySignal:
        n = int(self.params["lookback_bars"])
        if len(df) < n + 5:
            return StrategySignal(self.name, symbol, "HOLD", 0.0, "Insufficient data for breakout analysis", self.params)

        row = df.iloc[-1]
        close = float(row["close"])
        high = float(row["high"])
        low = float(row["low"])
        vol = float(row.get("volume", 0))

        # Lookback window excluding the latest bar
        prev_highs = [float(df.iloc[-i]["high"]) for i in range(2, n + 2)]
        prev_lows = [float(df.iloc[-i]["low"]) for i in range(2, n + 2)]
        highest_prev = max(prev_highs)
        lowest_prev = min(prev_lows)

        vol_avg = sum(float(df.iloc[-i].get("volume", 0)) for i in range(2, n + 2)) / n

        # Breakout above lookback high with volume confirmation
        if close > highest_prev and vol >= vol_avg * 1.1:
            return StrategySignal(
                self.name,
                symbol,
                "BUY",
                0.85,
                f"Breakout above {n}-bar high (${highest_prev:.2f}) on {vol/vol_avg:.1f}x avg volume",
                self.params,
            )
        # Breakdown below lookback low with volume confirmation
        elif close < lowest_prev and vol >= vol_avg * 1.1:
            return StrategySignal(
                self.name,
                symbol,
                "SELL",
                0.85,
                f"Breakdown below {n}-bar low (${lowest_prev:.2f}) on {vol/vol_avg:.1f}x avg volume",
                self.params,
            )

        return StrategySignal(self.name, symbol, "HOLD", 0.0, "Consolidation within range", self.params)

