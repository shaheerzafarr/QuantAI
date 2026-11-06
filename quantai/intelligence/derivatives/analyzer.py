"""Derivatives & Futures Market Intelligence Analyzer."""

from dataclasses import dataclass
from typing import Dict, List, Optional
from quantai.ingestion.schema import DerivativesData


@dataclass
class DerivativesSignal:
    timestamp: str
    symbol: str
    funding_rate: float
    funding_bias: str  # OVERLEVERAGED_LONG, OVERLEVERAGED_SHORT, BALANCED
    open_interest: float
    oi_change_pct: float
    long_short_ratio: float
    liquidation_squeeze_risk: str  # HIGH_LONG_SQUEEZE, HIGH_SHORT_SQUEEZE, LOW
    futures_basis_bps: float
    summary_bias: str  # BULLISH, BEARISH, NEUTRAL


class DerivativesAnalyzer:
    """Evaluates funding rate pressure, open interest, and liquidation cascades."""

    def __init__(self, extreme_funding_threshold: float = 0.0004):
        self.extreme_funding = extreme_funding_threshold
        self._prev_oi: Dict[str, float] = {}

    def analyze(self, data: DerivativesData) -> DerivativesSignal:
        prev_oi = self._prev_oi.get(data.symbol, data.open_interest)
        oi_change_pct = (
            (data.open_interest - prev_oi) / (prev_oi + 1e-10)
        ) if prev_oi > 0 else 0.0
        self._prev_oi[data.symbol] = data.open_interest

        # 1. Funding Rate Analysis
        # Positive funding: longs pay shorts. Extreme positive => crowded long squeeze risk.
        if data.funding_rate >= self.extreme_funding:
            funding_bias = "OVERLEVERAGED_LONG"
        elif data.funding_rate <= -self.extreme_funding:
            funding_bias = "OVERLEVERAGED_SHORT"
        else:
            funding_bias = "BALANCED"

        # 2. Liquidation Squeeze Detection
        if funding_bias == "OVERLEVERAGED_LONG" and data.long_short_ratio > 2.2:
            squeeze_risk = "HIGH_LONG_SQUEEZE"  # Risk of long liquidation cascading down
            summary_bias = "BEARISH"
        elif funding_bias == "OVERLEVERAGED_SHORT" and data.long_short_ratio < 0.6:
            squeeze_risk = "HIGH_SHORT_SQUEEZE"  # Squeeze fuel to upside
            summary_bias = "BULLISH"
        else:
            squeeze_risk = "LOW"
            if data.funding_rate > 0 and oi_change_pct > 0.02:
                summary_bias = "BULLISH"
            elif data.funding_rate < 0 and oi_change_pct > 0.02:
                summary_bias = "BEARISH"
            else:
                summary_bias = "NEUTRAL"

        return DerivativesSignal(
            timestamp=data.event_time.isoformat(),
            symbol=data.symbol,
            funding_rate=data.funding_rate,
            funding_bias=funding_bias,
            open_interest=data.open_interest,
            oi_change_pct=float(oi_change_pct),
            long_short_ratio=data.long_short_ratio,
            liquidation_squeeze_risk=squeeze_risk,
            futures_basis_bps=data.futures_basis_bps,
            summary_bias=summary_bias,
        )
