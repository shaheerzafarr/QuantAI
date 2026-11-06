"""Multi-Agent Swarm Orchestrator."""

from typing import Any, Dict, List
from quantai.agents.base import BaseAnalyst, AgentReport
from quantai.agents.specialists import (
    WhaleAnalyst,
    TechnicalAnalyst,
    QuantAnalyst,
    DerivativesAnalyst,
    LiquidityAnalyst,
    SentimentAnalyst,
    MacroAnalyst,
    AdversarialAnalyst,
    RiskAnalyst,
    PortfolioAnalyst,
    ResearchAnalyst,
    ExecutionAnalyst,
)


class MultiAgentSwarm:
    """Orchestrates 12 specialized analytical agents to generate decentralized market intelligence."""

    def __init__(self):
        self.analysts: List[BaseAnalyst] = [
            WhaleAnalyst(),
            TechnicalAnalyst(),
            QuantAnalyst(),
            DerivativesAnalyst(),
            LiquidityAnalyst(),
            SentimentAnalyst(),
            MacroAnalyst(),
            AdversarialAnalyst(),
            RiskAnalyst(),
            PortfolioAnalyst(),
            ResearchAnalyst(),
            ExecutionAnalyst(),
        ]

    def run_swarm(self, context: Dict[str, Any]) -> List[AgentReport]:
        """Dispatches context to all agents and collects their structured reports."""
        reports: List[AgentReport] = []

        # Run primary analysts first
        for analyst in self.analysts:
            if isinstance(analyst, AdversarialAnalyst):
                continue
            rep = analyst.evaluate(context)
            reports.append(rep)

        # Determine preliminary consensus
        bulls = sum(1 for r in reports if r.bias == "BULLISH")
        bears = sum(1 for r in reports if r.bias == "BEARISH")
        consensus = "BULLISH" if bulls > bears else ("BEARISH" if bears > bulls else "NEUTRAL")

        # Now pass consensus to Adversarial Analyst to actively challenge the view
        adv_context = dict(context)
        adv_context["consensus_hint"] = consensus
        for analyst in self.analysts:
            if isinstance(analyst, AdversarialAnalyst):
                adv_rep = analyst.evaluate(adv_context)
                reports.append(adv_rep)

        return reports
