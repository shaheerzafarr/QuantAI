"""Unit Tests for Independent Risk Guardian."""

import pytest
from quantai.decision.engine import TradeDecision
from quantai.risk.guardian import IndependentRiskGuardian


@pytest.fixture
def risk_guardian():
    return IndependentRiskGuardian(initial_capital_usd=100_000.0)


def test_fractional_kelly_sizing(risk_guardian):
    # p = 0.65, b = 2.0 -> Kelly full = (0.65 * 2 - 0.35) / 2 = 0.95 / 2 = 0.475
    # Fractional Kelly (0.35x) = 0.166 -> capped by max risk * 3 (3%) = $3,000
    alloc = risk_guardian.calculate_position_size(
        current_price=68000.0,
        win_prob=0.65,
        expected_win_loss_ratio=2.0,
    )
    assert 1000.0 <= alloc <= 3000.0


def test_exposure_limit_veto(risk_guardian):
    # Set active exposure to 50%
    risk_guardian.update_portfolio_state(
        current_total_usd=100_000.0,
        active_exposure_usd=50_000.0,
    )

    decision = TradeDecision(
        pair="BTC/USDT",
        timestamp="2026-01-01T00:00:00Z",
        action="BUY",
        confidence=0.85,
        expected_return_bps=45.0,
        expected_risk_bps=150.0,
        estimated_cost_bps=18.0,
        supporting_evidence=["Strong momentum"],
        contradictory_evidence=[],
        selected_strategy="MultiAgent_ML_Fusion",
        model_version="v1",
        risk_status="PENDING_RISK_CHECK",
        explanation="Testing veto",
    )

    verdict = risk_guardian.evaluate_decision(decision, current_price=68000.0)
    assert not verdict.approved
    assert "exposure" in verdict.veto_reason.lower()


def test_emergency_halt_on_drawdown(risk_guardian):
    # Simulate a severe drawdown exceeding 6%
    risk_guardian.update_portfolio_state(
        current_total_usd=93_000.0,  # 7% drop from peak 100k
        active_exposure_usd=10_000.0,
    )
    assert risk_guardian.emergency_halt

    decision = TradeDecision(
        pair="BTC/USDT",
        timestamp="2026-01-01T00:00:00Z",
        action="BUY",
        confidence=0.90,
        expected_return_bps=50.0,
        expected_risk_bps=150.0,
        estimated_cost_bps=18.0,
        supporting_evidence=[],
        contradictory_evidence=[],
        selected_strategy="MultiAgent_ML_Fusion",
        model_version="v1",
        risk_status="PENDING_RISK_CHECK",
        explanation="Testing circuit breaker",
    )
    verdict = risk_guardian.evaluate_decision(decision, current_price=68000.0)
    assert not verdict.approved
    assert "emergency circuit breaker" in verdict.veto_reason.lower()
