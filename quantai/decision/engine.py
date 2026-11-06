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

    def __init__(self, min_confidence: float = 0.55, min_expected_edge_bps: float = 8.0):
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
        supporting: List[str] = []
        contradictory: List[str] = []

        # 1. Bayesian Swarm Consensus Probability
        swarm_weighted_prob = 0.0
        total_agent_weight = 0.0

        for r in agent_reports:
            weight = 1.0
            if r.agent_name in ["WhaleAnalyst", "LiquidityAnalyst", "OrderFlowAnalyst"]:
                weight = 1.25  # High-priority direct on-chain & book data
            elif r.agent_name in ["AdversarialAnalyst"]:
                weight = 1.15  # Devil's advocate risk check

            if r.bias == "BULLISH":
                agent_prob = 0.50 + (r.confidence * 0.45)
                supporting.append(f"[{r.agent_name}] {', '.join(r.key_findings[:2])}")
            elif r.bias == "BEARISH":
                agent_prob = 0.50 - (r.confidence * 0.45)
                contradictory.append(f"[{r.agent_name}] {', '.join(r.key_findings[:2])}")
            else:
                agent_prob = 0.50

            swarm_weighted_prob += agent_prob * weight
            total_agent_weight += weight

        p_swarm = swarm_weighted_prob / (total_agent_weight + 1e-10)

        # 2. Quantitative Strategy Signals
        p_strat = 0.50
        active_strategies: List[str] = []
        if strategy_signals:
            strat_weighted_prob = 0.0
            total_strat_weight = 0.0
            for s in strategy_signals:
                if s.action == "BUY" and s.strength > 0:
                    strat_p = 0.50 + (s.strength * 0.45)
                    supporting.append(f"[{s.strategy_name}] {s.rationale} (Strength: {s.strength:.0%})")
                    active_strategies.append(s.strategy_name)
                    strat_weighted_prob += strat_p * (1.0 + s.strength)
                    total_strat_weight += (1.0 + s.strength)
                elif s.action == "SELL" and s.strength > 0:
                    strat_p = 0.50 - (s.strength * 0.45)
                    contradictory.append(f"[{s.strategy_name}] {s.rationale} (Strength: {s.strength:.0%})")
                    active_strategies.append(s.strategy_name)
                    strat_weighted_prob += strat_p * (1.0 + s.strength)
                    total_strat_weight += (1.0 + s.strength)
                else:
                    strat_weighted_prob += 0.50 * 0.5
                    total_strat_weight += 0.5

            if total_strat_weight > 0:
                p_strat = strat_weighted_prob / total_strat_weight

        # 3. Machine Learning Model Prediction
        p_ml = 0.50
        ml_ver = "none"
        if ml_prediction:
            ml_ver = ml_prediction.model_version
            if ml_prediction.target_class == "BUY":
                p_ml = ml_prediction.calibrated_prob
                supporting.append(f"[ML Model] Calibrated BUY probability: {ml_prediction.calibrated_prob:.1%}")
            elif ml_prediction.target_class == "SELL":
                p_ml = 1.0 - ml_prediction.calibrated_prob
                contradictory.append(f"[ML Model] Calibrated SELL probability: {1.0 - ml_prediction.calibrated_prob:.1%}")

        # 4. Synthesize Combined Probability
        if active_strategies:
            # When active quantitative strategies fire, weight strategy + swarm + ML
            p_combined = (0.45 * p_strat) + (0.35 * p_swarm) + (0.20 * p_ml)
            strategy_name = " + ".join(active_strategies)
        else:
            p_combined = (0.65 * p_swarm) + (0.35 * p_ml)
            strategy_name = "MultiAgent_ML_Fusion"

        # 5. Economic Hurdle & Edge Calculation
        total_cost_bps = exchange_fee_bps * 2 + estimated_slippage_bps  # roundtrip fees + slippage

        if p_combined > 0.50:
            confidence = p_combined
            gross_edge_bps = (confidence - 0.50) * 450.0  # Scaled to expected swing move basis points
            net_edge_bps = gross_edge_bps - total_cost_bps

            if confidence >= self.min_confidence and net_edge_bps >= self.min_edge_bps:
                action = "BUY"
                explanation = (
                    f"Strong bullish confluence across {len(supporting)} signals ({strategy_name}) with net edge of {net_edge_bps:.1f} bps."
                )
            elif confidence >= self.min_confidence:
                action = "NO_TRADE"
                explanation = (
                    f"Bullish signal detected ({gross_edge_bps:.1f} bps) but insufficient to clear trading costs ({total_cost_bps:.1f} bps)."
                )
            else:
                action = "HOLD"
                explanation = "Bullish lean present but overall confidence below actionable threshold."
        elif p_combined < 0.50:
            confidence = 1.0 - p_combined
            gross_edge_bps = (confidence - 0.50) * 450.0
            net_edge_bps = gross_edge_bps - total_cost_bps

            if confidence >= self.min_confidence and net_edge_bps >= self.min_edge_bps:
                action = "SELL"
                explanation = (
                    f"Strong bearish breakdown signaled by {len(contradictory)} indicators ({strategy_name}). Net edge: {net_edge_bps:.1f} bps."
                )
            elif confidence >= self.min_confidence:
                action = "NO_TRADE"
                explanation = "Bearish bias detected but expected net edge does not exceed cost hurdle."
            else:
                action = "HOLD"
                explanation = "Bearish lean present but overall confidence below actionable threshold."
        else:
            confidence = 0.50
            gross_edge_bps = 0.0
            net_edge_bps = 0.0
            action = "HOLD"
            explanation = "Complete signal equilibrium or lack of market conviction. Capital preservation active."

        decision = TradeDecision(
            pair=symbol,
            timestamp=datetime.now(timezone.utc).isoformat(),
            action=action,
            confidence=round(confidence, 3),
            expected_return_bps=round(net_edge_bps, 2),
            expected_risk_bps=round(total_cost_bps + 150.0, 2),  # 150 bps stop loss
            estimated_cost_bps=round(total_cost_bps, 2),
            supporting_evidence=supporting[:6],
            contradictory_evidence=contradictory[:6],
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

