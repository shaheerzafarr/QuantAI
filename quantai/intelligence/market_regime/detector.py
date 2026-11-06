"""Market Regime Detection Engine."""

from dataclasses import dataclass
from enum import Enum
import numpy as np
from quantai.common import pd


class MarketRegime(str, Enum):
    TRENDING_BULL = "TRENDING_BULL"
    TRENDING_BEAR = "TRENDING_BEAR"
    VOLATILE_CHOP = "VOLATILE_CHOP"
    RANGING_COMPRESSION = "RANGING_COMPRESSION"


@dataclass
class RegimeState:
    regime: MarketRegime
    trend_strength: float  # 0.0 to 1.0
    volatility_percentile: float  # 0.0 to 1.0
    recommended_strategy_family: str  # TREND_FOLLOWING, MEAN_REVERSION, BREAKOUT


class MarketRegimeDetector:
    """Classifies current market structure into statistical and volatility regimes."""

    def detect_regime(self, df: pd.DataFrame) -> RegimeState:
        if len(df) < 50:
            return RegimeState(
                regime=MarketRegime.RANGING_COMPRESSION,
                trend_strength=0.2,
                volatility_percentile=0.5,
                recommended_strategy_family="MEAN_REVERSION",
            )

        recent = df.iloc[-1]
        close = recent["close"]
        ema20 = recent.get("ema_20", close)
        ema50 = recent.get("ema_50", close)
        ema200 = recent.get("ema_200", close)

        # Volatility percentile based on ATR / price
        vol_ratio = df["atr_14"] / (df["close"] + 1e-10)
        recent_vol = vol_ratio.iloc[-1]
        vol_pct = float((vol_ratio < recent_vol).mean())

        # Trend strength: distance between EMAs
        trend_spread = (ema20 - ema50) / (close + 1e-10)
        trend_strength = float(min(1.0, abs(trend_spread) * 50.0))

        # Classification rules
        if vol_pct > 0.85:
            regime = MarketRegime.VOLATILE_CHOP
            strategy_family = "MEAN_REVERSION"
        elif close > ema50 > ema200 and trend_spread > 0.005:
            regime = MarketRegime.TRENDING_BULL
            strategy_family = "TREND_FOLLOWING"
        elif close < ema50 < ema200 and trend_spread < -0.005:
            regime = MarketRegime.TRENDING_BEAR
            strategy_family = "TREND_FOLLOWING"
        elif vol_pct < 0.25:
            regime = MarketRegime.RANGING_COMPRESSION
            strategy_family = "BREAKOUT"
        else:
            regime = MarketRegime.RANGING_COMPRESSION
            strategy_family = "MEAN_REVERSION"

        return RegimeState(
            regime=regime,
            trend_strength=trend_strength,
            volatility_percentile=vol_pct,
            recommended_strategy_family=strategy_family,
        )
