"""Order-Flow & Liquidity Intelligence Analyzer."""

from dataclasses import dataclass
from typing import Dict, List, Optional
import numpy as np
from quantai.ingestion.schema import OrderBookDepth, TradeData


@dataclass
class OrderFlowSignal:
    timestamp: str
    symbol: str
    bid_ask_imbalance: float  # -1.0 (heavy ask) to +1.0 (heavy bid)
    cumulative_volume_delta: float
    aggressive_buyer_ratio: float
    absorption_detected: bool
    estimated_slippage_bps: float
    liquidity_clusters: List[float]
    summary_bias: str  # BULLISH, BEARISH, NEUTRAL


class OrderFlowAnalyzer:
    """Analyzes real-time and snapshot orderbook & trade flow dynamics."""

    def __init__(self, imbalance_threshold: float = 0.60):
        self.imbalance_threshold = imbalance_threshold
        self._cvd_history: Dict[str, float] = {}

    def analyze_orderbook_depth(self, depth: OrderBookDepth) -> Dict[str, float]:
        """Calculates orderbook depth metrics, weighted spreads, and multi-level imbalance."""
        total_bid_vol = depth.bid_depth_10
        total_ask_vol = depth.ask_depth_10
        total_vol = total_bid_vol + total_ask_vol + 1e-10

        # Imbalance ratio: +1 = 100% bids, -1 = 100% asks
        imbalance = (total_bid_vol - total_ask_vol) / total_vol

        # Detect top 3 liquidity clusters in order book
        clusters = []
        if depth.bids:
            sorted_bids = sorted(depth.bids, key=lambda x: x[1], reverse=True)
            clusters.extend([b[0] for b in sorted_bids[:2]])
        if depth.asks:
            sorted_asks = sorted(depth.asks, key=lambda x: x[1], reverse=True)
            clusters.extend([a[0] for a in sorted_asks[:2]])

        # Estimate market impact / slippage in basis points for standard $50k size
        standard_order_usd = 50_000.0
        slippage_bps = (depth.spread / (depth.best_bid + 1e-10)) * 10_000
        if total_ask_vol < standard_order_usd * 2:
            slippage_bps += 5.0  # Thin book premium

        return {
            "imbalance": float(imbalance),
            "spread": float(depth.spread),
            "slippage_bps": float(slippage_bps),
            "bid_depth_usd": float(total_bid_vol),
            "ask_depth_usd": float(total_ask_vol),
            "clusters": clusters,
        }

    def compute_trade_delta(
        self, symbol: str, trades: List[TradeData]
    ) -> Dict[str, float]:
        """Calculates aggressive buy vs sell volume delta and updates running CVD."""
        buy_vol = sum(t.amount * t.price for t in trades if t.side.lower() == "buy")
        sell_vol = sum(t.amount * t.price for t in trades if t.side.lower() == "sell")
        delta = buy_vol - sell_vol
        total_vol = buy_vol + sell_vol + 1e-10

        running_cvd = self._cvd_history.get(symbol, 0.0) + delta
        self._cvd_history[symbol] = running_cvd

        buyer_ratio = buy_vol / total_vol
        absorption = False
        # Absorption: large aggressive selling or buying with minimal price progress
        if total_vol > 500_000 and 0.45 < buyer_ratio < 0.55:
            absorption = True

        return {
            "buy_vol_usd": float(buy_vol),
            "sell_vol_usd": float(sell_vol),
            "delta_usd": float(delta),
            "buyer_ratio": float(buyer_ratio),
            "running_cvd": float(running_cvd),
            "absorption": absorption,
        }

    def evaluate_signal(
        self,
        symbol: str,
        depth: OrderBookDepth,
        trades: Optional[List[TradeData]] = None,
    ) -> OrderFlowSignal:
        """Combines depth and trades into a standardized OrderFlowSignal."""
        depth_metrics = self.analyze_orderbook_depth(depth)

        if trades:
            trade_metrics = self.compute_trade_delta(symbol, trades)
        else:
            trade_metrics = {
                "buyer_ratio": 0.50,
                "running_cvd": self._cvd_history.get(symbol, 0.0),
                "absorption": False,
            }

        imbalance = depth_metrics["imbalance"]
        buyer_ratio = trade_metrics["buyer_ratio"]

        # Synthesize bias
        if imbalance > 0.20 and buyer_ratio > 0.55:
            bias = "BULLISH"
        elif imbalance < -0.20 and buyer_ratio < 0.45:
            bias = "BEARISH"
        else:
            bias = "NEUTRAL"

        return OrderFlowSignal(
            timestamp=depth.event_time.isoformat(),
            symbol=symbol,
            bid_ask_imbalance=imbalance,
            cumulative_volume_delta=trade_metrics["running_cvd"],
            aggressive_buyer_ratio=buyer_ratio,
            absorption_detected=trade_metrics["absorption"],
            estimated_slippage_bps=depth_metrics["slippage_bps"],
            liquidity_clusters=depth_metrics["clusters"],
            summary_bias=bias,
        )

