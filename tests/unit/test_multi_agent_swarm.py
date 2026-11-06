"""Unit Tests for Multi-Agent Swarm Intelligence."""

import pytest
from quantai.agents.swarm import MultiAgentSwarm


def test_multi_agent_swarm_execution():
    swarm = MultiAgentSwarm()
    assert len(swarm.analysts) == 12

    context = {
        "symbol": "BTC/USDT",
        "hurst_exponent": 0.62,
        "price_zscore": 1.2,
        "spread": 0.01,
        "estimated_slippage_bps": 2.0,
    }

    reports = swarm.run_swarm(context)
    assert len(reports) == 12

    agent_names = [r.agent_name for r in reports]
    assert "WhaleAnalyst" in agent_names
    assert "AdversarialAnalyst" in agent_names
    assert "RiskAnalyst" in agent_names
    assert "TechnicalAnalyst" in agent_names

    # Check that each report adheres strictly to the contract
    for r in reports:
        assert r.bias in ["BULLISH", "BEARISH", "NEUTRAL"]
        assert 0.0 <= r.confidence <= 1.0
        assert r.actionable_recommendation in ["BUY", "SELL", "HOLD"]
