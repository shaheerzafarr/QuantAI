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


class MACDDivergenceStrategy(BaseStrategy):
    """Detects classical price vs momentum divergence on MACD histogram."""

    def __init__(self, lookback_bars: int = 12):
        super().__init__(
            name="MACD_Divergence",
            params={"lookback_bars": float(lookback_bars)},
        )

    def generate_signal(self, df: pd.DataFrame, symbol: str = "BTC/USDT") -> StrategySignal:
        n = int(self.params["lookback_bars"])
        if len(df) < n + 15:
            return StrategySignal(self.name, symbol, "HOLD", 0.0, "Insufficient bars for divergence analysis", self.params)

        row = df.iloc[-1]
        prev_row = df.iloc[-n]

        close = float(row["close"])
        prev_close = float(prev_row["close"])

        macd_hist = float(row.get("macd_hist", 0.0))
        prev_macd_hist = float(prev_row.get("macd_hist", 0.0))

        # Bullish Divergence: Lower price low + Higher MACD momentum low
        if close < prev_close and macd_hist > prev_macd_hist and macd_hist > float(df.iloc[-2].get("macd_hist", 0.0)):
            return StrategySignal(
                self.name,
                symbol,
                "BUY",
                0.80,
                f"Bullish MACD Divergence: Price Lower Low (${close:.2f} < ${prev_close:.2f}) vs MACD Hist Higher Low",
                self.params,
            )
        # Bearish Divergence: Higher price high + Lower MACD momentum high
        elif close > prev_close and macd_hist < prev_macd_hist and macd_hist < float(df.iloc[-2].get("macd_hist", 0.0)):
            return StrategySignal(
                self.name,
                symbol,
                "SELL",
                0.80,
                f"Bearish MACD Divergence: Price Higher High (${close:.2f} > ${prev_close:.2f}) vs MACD Hist Lower High",
                self.params,
            )

        return StrategySignal(self.name, symbol, "HOLD", 0.0, "No divergence detected", self.params)


class CandlestickPatternStrategy(BaseStrategy):
    """Identifies high-probability reversal candlestick structures (Engulfing, Hammer Pin Bars)."""

    def __init__(self):
        super().__init__(name="CandlestickReversal_Structure")

    def generate_signal(self, df: pd.DataFrame, symbol: str = "BTC/USDT") -> StrategySignal:
        if len(df) < 5:
            return StrategySignal(self.name, symbol, "HOLD", 0.0, "Insufficient bars", self.params)

        curr = df.iloc[-1]
        prev = df.iloc[-2]

        c_open = float(curr["open"])
        c_high = float(curr["high"])
        c_low = float(curr["low"])
        c_close = float(curr["close"])

        p_open = float(prev["open"])
        p_close = float(prev["close"])

        c_body = abs(c_close - c_open)
        p_body = abs(p_close - p_open)
        total_range = c_high - c_low + 1e-10
        lower_wick = min(c_open, c_close) - c_low
        upper_wick = c_high - max(c_open, c_close)

        # 1. Bullish Engulfing
        if p_close < p_open and c_close > c_open and c_close >= p_open and c_open <= p_close and c_body > p_body * 1.2:
            return StrategySignal(
                self.name, symbol, "BUY", 0.80, "Bullish Engulfing reversal bar confirmed at support", self.params
            )

        # 2. Bearish Engulfing
        elif p_close > p_open and c_close < c_open and c_close <= p_open and c_open >= p_close and c_body > p_body * 1.2:
            return StrategySignal(
                self.name, symbol, "SELL", 0.80, "Bearish Engulfing rejection bar confirmed at resistance", self.params
            )

        # 3. Bullish Hammer / Pin Bar at Lows
        elif lower_wick >= c_body * 2.0 and upper_wick <= c_body * 0.5 and (c_close - c_low) / total_range >= 0.65:
            return StrategySignal(
                self.name, symbol, "BUY", 0.75, f"Bullish Hammer Pin Bar rejection ({lower_wick:.1f} lower wick)", self.params
            )

        return StrategySignal(self.name, symbol, "HOLD", 0.0, "Standard candlestick structure", self.params)


class RangeCompressionScalper(BaseStrategy):
    """Exploits price oscillation within tight compression ranges using Stochastic RSI & 1.5-sigma Bollinger Bands."""

    def __init__(self, stoch_oversold: float = 25.0, stoch_overbought: float = 75.0, min_rr: float = 2.0):
        super().__init__(
            name="RangeCompressionScalper",
            params={
                "stoch_oversold": float(stoch_oversold),
                "stoch_overbought": float(stoch_overbought),
                "min_rr": float(min_rr),
            },
        )

    def generate_signal(self, df: pd.DataFrame, symbol: str = "BTC/USDT") -> StrategySignal:
        if len(df) < 25:
            return StrategySignal(self.name, symbol, "HOLD", 0.0, "Insufficient bars", self.params)

        curr = df.iloc[-1]
        prev = df.iloc[-2]

        close = float(curr["close"])
        low = float(curr["low"])
        high = float(curr["high"])

        bb_mid = float(curr.get("bb_mid", close))
        bb_upper_1_5 = float(curr.get("bb_upper_1_5", close * 1.01))
        bb_lower_1_5 = float(curr.get("bb_lower_1_5", close * 0.99))
        stoch_k = float(curr.get("stoch_rsi_k", 50.0))
        stoch_d = float(curr.get("stoch_rsi_d", 50.0))
        prev_k = float(prev.get("stoch_rsi_k", 50.0))
        rsi_14 = float(curr.get("rsi_14", 50.0))

        if bb_upper_1_5 <= bb_lower_1_5:
            return StrategySignal(self.name, symbol, "HOLD", 0.0, "Invalid band width", self.params)

        # 1. Bullish Mean-Reversion at Support (BUY)
        near_lower_band = close <= bb_lower_1_5 * 1.0015 or low <= bb_lower_1_5
        stoch_oversold_signal = stoch_k <= self.params["stoch_oversold"] or (stoch_k <= 35.0 and stoch_k > prev_k)

        if near_lower_band and (stoch_oversold_signal or rsi_14 < 38.0):
            dist_to_mid = max(0.0, (bb_mid - close) / (close + 1e-10))
            tp_pct = round(max(0.006, min(0.022, dist_to_mid if dist_to_mid > 0.004 else 0.008)), 4)
            sl_pct = round(tp_pct / self.params["min_rr"], 4)

            sig_params = {
                **self.params,
                "tp_pct": tp_pct,
                "sl_pct": sl_pct,
                "stoch_k": round(stoch_k, 2),
                "stoch_d": round(stoch_d, 2),
                "target_midline": round(bb_mid, 2),
            }
            return StrategySignal(
                self.name,
                symbol,
                "BUY",
                0.85,
                f"Range Compression Bounce: Price (${close:.2f}) at lower 1.5-sigma band (${bb_lower_1_5:.2f}) with oversold StochRSI ({stoch_k:.1f})",
                sig_params,
            )

        # 2. Bearish Mean-Reversion at Resistance (SELL)
        near_upper_band = close >= bb_upper_1_5 * 0.9985 or high >= bb_upper_1_5
        stoch_overbought_signal = stoch_k >= self.params["stoch_overbought"] or (stoch_k >= 65.0 and stoch_k < prev_k)

        if near_upper_band and (stoch_overbought_signal or rsi_14 > 62.0):
            dist_to_mid = max(0.0, (close - bb_mid) / (close + 1e-10))
            tp_pct = round(max(0.006, min(0.022, dist_to_mid if dist_to_mid > 0.004 else 0.008)), 4)
            sl_pct = round(tp_pct / self.params["min_rr"], 4)

            sig_params = {
                **self.params,
                "tp_pct": tp_pct,
                "sl_pct": sl_pct,
                "stoch_k": round(stoch_k, 2),
                "stoch_d": round(stoch_d, 2),
                "target_midline": round(bb_mid, 2),
            }
            return StrategySignal(
                self.name,
                symbol,
                "SELL",
                0.85,
                f"Range Compression Rejection: Price (${close:.2f}) at upper 1.5-sigma band (${bb_upper_1_5:.2f}) with overbought StochRSI ({stoch_k:.1f})",
                sig_params,
            )

        return StrategySignal(self.name, symbol, "HOLD", 0.0, "Oscillating within inner range bounds", self.params)



