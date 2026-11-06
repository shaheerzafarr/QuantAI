"""Decision and Signal Fusion Engine."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from quantai.agents.base import AgentReport
from quantai.ml.pipeline import MLPrediction
from quantai.research.strategies import StrategySignal
from quantai.storage.db import get_db_manager
from quantai.storage.models import TradeDecisionRecord


@dataclass
class TradeDecision:
    pair: str
    timestamp: str
    action: str  # BUY, SELL, HOLD, NO_TRADE
    confidence: float
    expected_return_bps: float
    expected_risk_bps: float
    estimated_cost_bps: float
    supporting_evidence: List[str]
    contradictory_evidence: List[str]
    selected_strategy: str
    model_version: str
    risk_status: str  # PENDING_RISK_CHECK, APPROVED, VETOED
    explanation: str


class DecisionFusionEngine:
    """Fuses Multi-Agent reports, ML predictions, and quantitative strategy signals."""

    def __init__(self, min_confidence: float = 0.65, min_expected_edge_bps: float = 15.0):
        self.min_confidence = min_confidence
        self.min_edge_bps = min_expected_edge_bps
        self.db_manager = get_db_manager()

    def fuse_signals(
        self,
        symbol: str,
        agent_reports: List[AgentReport],
        ml_prediction: Optional[MLPrediction] = None,
        strategy_signals: Optional[List[StrategySignal]] = None,
        estimated_slippage_bps: float = 3.0,
        exchange_fee_bps: float = 7.5,
    ) -> TradeDecision:
        """Synthesizes all intelligence layers into an auditable trade decision."""
        supporting = []
        contradictory = []

        # 1. Weight Agent Signals (Correlated clustering discount)
        bullish_score = 0.0
        bearish_score = 0.0
        total_weight = 0.0

        for r in agent_reports:
            # Discount heavily correlated agents
            weight = 1.0
            if r.agent_name in ["WhaleAnalyst", "LiquidityAnalyst"]:
                weight = 1.2  # High value direct orderflow/chain data
            elif r.agent_name in ["AdversarialAnalyst"]:
                weight = 1.1

            if r.bias == "BULLISH":
                bullish_score += r.confidence * weight
                supporting.append(f"[{r.agent_name}] {', '.join(r.key_findings[:2])}")
            elif r.bias == "BEARISH":
                bearish_score += r.confidence * weight
                contradictory.append(f"[{r.agent_name}] {', '.join(r.key_findings[:2])}")

            total_weight += weight

        norm_bull = bullish_score / (total_weight + 1e-10)
        norm_bear = bearish_score / (total_weight + 1e-10)

        # 2. Integrate Machine Learning Prediction
        ml_ver = "none"
        if ml_prediction:
            ml_ver = ml_prediction.model_version
            if ml_prediction.target_class == "BUY":
                norm_bull += ml_prediction.calibrated_prob * 0.4
                supporting.append(f"[ML Model] Calibrated BUY probability: {ml_prediction.calibrated_prob:.1%}")
            elif ml_prediction.target_class == "SELL":
                norm_bear += (1 - ml_prediction.calibrated_prob) * 0.4
                contradictory.append(f"[ML Model] Calibrated SELL probability: {1 - ml_prediction.calibrated_prob:.1%}")

        # 3. Transaction Cost Filter
        total_cost_bps = exchange_fee_bps * 2 + estimated_slippage_bps  # roundtrip fees + slippage

        # 4. Determine Action & Edge
        strategy_name = "MultiAgent_ML_Fusion"
        if norm_bull > norm_bear and norm_bull >= self.min_confidence:
            gross_edge_bps = (norm_bull - 0.50) * 80.0
            net_edge_bps = gross_edge_bps - total_cost_bps
            confidence = min(0.95, norm_bull)

            if net_edge_bps >= self.min_edge_bps:
                action = "BUY"
                explanation = (
                    f"Strong bullish convergence across {len(supporting)} signals with net edge of {net_edge_bps:.1f} bps."
                )
            else:
                action = "NO_TRADE"
                explanation = f"Bullish signal detected ({gross_edge_bps:.1f} bps) but insufficient to clear trading costs ({total_cost_bps:.1f} bps)."
        elif norm_bear > norm_bull and norm_bear >= self.min_confidence:
            gross_edge_bps = (norm_bear - 0.50) * 80.0
            net_edge_bps = gross_edge_bps - total_cost_bps
            confidence = min(0.95, norm_bear)

            if net_edge_bps >= self.min_edge_bps:
                action = "SELL"
                explanation = (
                    f"Strong bearish breakdown signaled by {len(contradictory)} agents. Exit / hedge recommended."
                )
            else:
                action = "NO_TRADE"
                explanation = "Bearish bias detected but expected net edge does not exceed cost hurdle."
        else:
            action = "HOLD"
            confidence = max(norm_bull, norm_bear)
            gross_edge_bps = 0.0
            net_edge_bps = 0.0
            explanation = "Signal disagreement or low confidence across analytical swarm. Maintaining capital preservation."

        decision = TradeDecision(
            pair=symbol,
            timestamp=datetime.now(timezone.utc).isoformat(),
            action=action,
            confidence=round(confidence, 3),
            expected_return_bps=round(net_edge_bps, 2),
            expected_risk_bps=round(total_cost_bps + 150.0, 2),  # 150 bps typical stop loss
            estimated_cost_bps=round(total_cost_bps, 2),
            supporting_evidence=supporting[:5],
            contradictory_evidence=contradictory[:5],
            selected_strategy=strategy_name,
            model_version=ml_ver,
            risk_status="PENDING_RISK_CHECK",
            explanation=explanation,
        )

        # Log decision to database
        try:
            with self.db_manager.get_session() as session:
                rec = TradeDecisionRecord(
                    pair=decision.pair,
                    timestamp=datetime.now(timezone.utc),
                    action=decision.action,
                    confidence=decision.confidence,
                    expected_return_bps=decision.expected_return_bps,
                    expected_risk_bps=decision.expected_risk_bps,
                    supporting_evidence=decision.supporting_evidence,
                    contradictory_evidence=decision.contradictory_evidence,
                    risk_status=decision.risk_status,
                    explanation=decision.explanation,
                )
                session.add(rec)
        except Exception:
            pass

        return decision
