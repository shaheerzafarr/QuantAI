"""Macroeconomic & Cross-Market Intelligence Analyzer."""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class MacroSignal:
    timestamp: str
    dxy_index: float
    dxy_trend: str  # BULLISH (headwind for crypto), BEARISH (tailwind for crypto)
    sp500_trend: str
    fed_rate_posture: str  # HAWKISH, DOVISH, NEUTRAL
    btc_dominance: float
    stablecoin_supply_change_pct: float
    crypto_macro_tailwind: str  # STRONG_TAILWIND, MODERATE, HEADWIND


class MacroAnalyzer:
    """Evaluates macro monetary indicators and traditional financial market linkages."""

    def __init__(self):
        # Baseline reference macro metrics
        self._dxy = 104.2
        self._fed_posture = "NEUTRAL"
        self._btc_dom = 56.4
        self._stable_growth = 0.5  # % change 30d

    def update_metrics(
        self,
        dxy: float,
        fed_posture: str = "NEUTRAL",
        btc_dom: float = 56.0,
        stable_growth: float = 0.5,
    ):
        self._dxy = dxy
        self._fed_posture = fed_posture
        self._btc_dom = btc_dom
        self._stable_growth = stable_growth

    def evaluate(self, timestamp: str = "") -> MacroSignal:
        # DXY > 105 is typically a risk-asset headwind; DXY falling is a tailwind
        dxy_trend = "BULLISH" if self._dxy > 105.0 else ("BEARISH" if self._dxy < 102.0 else "NEUTRAL")

        # Crypto macro tailwind synthesis
        score = 0
        if dxy_trend == "BEARISH":
            score += 1
        elif dxy_trend == "BULLISH":
            score -= 1

        if self._fed_posture == "DOVISH":
            score += 2
        elif self._fed_posture == "HAWKISH":
            score -= 2

        if self._stable_growth > 0:
            score += 1

        if score >= 2:
            tailwind = "STRONG_TAILWIND"
        elif score <= -2:
            tailwind = "HEADWIND"
        else:
            tailwind = "MODERATE"

        return MacroSignal(
            timestamp=timestamp,
            dxy_index=self._dxy,
            dxy_trend=dxy_trend,
            sp500_trend="BULLISH",
            fed_rate_posture=self._fed_posture,
            btc_dominance=self._btc_dom,
            stablecoin_supply_change_pct=self._stable_growth,
            crypto_macro_tailwind=tailwind,
        )

