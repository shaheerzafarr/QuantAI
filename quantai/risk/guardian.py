"""Independent Risk Guardian & Portfolio Sizing Engine.

Maintains final and absolute veto power over all AI and strategy trade decisions.
No model or agent can bypass or override these controls.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from quantai.config.settings import get_config
from quantai.decision.engine import TradeDecision
from quantai.storage.db import get_db_manager
from quantai.storage.models import RiskEvent, PortfolioSnapshot


@dataclass
class RiskVerdict:
    approved: bool
    pair: str
    action: str
    allocated_usd: float
    position_size_asset: float
    stop_loss_price: float
    take_profit_price: float
    risk_reward_ratio: float
    veto_reason: Optional[str] = None


class IndependentRiskGuardian:
    """Enforces mathematical risk limits, fractional Kelly sizing, and circuit breakers."""

    def __init__(self, initial_capital_usd: float = 100_000.0):
        self.config = get_config()
        self.risk_cfg = self.config.risk
        self.total_capital = initial_capital_usd
        self.available_capital = initial_capital_usd
        self.active_exposure_usd = 0.0
        self.peak_capital = initial_capital_usd
        self.daily_start_capital = initial_capital_usd
        self.emergency_halt = False
        self.db_manager = get_db_manager()

    def update_portfolio_state(
        self, current_total_usd: float, active_exposure_usd: float
    ):
        """Synchronizes live portfolio metrics and tracks drawdown."""
        self.total_capital = current_total_usd
        self.active_exposure_usd = active_exposure_usd
        self.available_capital = max(0.0, current_total_usd - active_exposure_usd)

        if current_total_usd > self.peak_capital:
            self.peak_capital = current_total_usd

        # Calculate drawdowns
        total_dd = (self.peak_capital - current_total_usd) / self.peak_capital
        daily_dd = (self.daily_start_capital - current_total_usd) / self.daily_start_capital

        # Enforce hard circuit breakers
        if self.risk_cfg.enforce_circuit_breakers:
            if total_dd >= self.risk_cfg.max_total_drawdown_pct:
                self.trigger_emergency_halt(f"Total drawdown reached {total_dd:.2%}, exceeding {self.risk_cfg.max_total_drawdown_pct:.2%}")
            elif daily_dd >= self.risk_cfg.max_daily_loss_pct:
                self.trigger_emergency_halt(f"Daily drawdown reached {daily_dd:.2%}, exceeding {self.risk_cfg.max_daily_loss_pct:.2%}")

    def trigger_emergency_halt(self, reason: str):
        """Immediately halts all execution and creates critical audit log."""
        self.emergency_halt = True
        try:
            with self.db_manager.get_session() as session:
                ev = RiskEvent(
                    event_type="EMERGENCY_HALT",
                    severity="critical",
                    reason=reason,
                    timestamp=datetime.now(timezone.utc),
                )
                session.add(ev)
        except Exception:
            pass

    def calculate_position_size(
        self,
        current_price: float,
        win_prob: float,
        expected_win_loss_ratio: float = 2.0,
    ) -> float:
        """
        Fractional Kelly Criterion:
        f* = (p * b - q) / b
        Scaled by configured conservative fractional multiplier (default 0.35).
        """
        p = max(0.01, min(0.99, win_prob))
        q = 1.0 - p
        b = max(0.5, expected_win_loss_ratio)

        kelly_full = (p * b - q) / b
        if kelly_full <= 0:
            return 0.0

        fractional_kelly = kelly_full * self.risk_cfg.kelly_fraction
        # Cap at single-trade max risk allocation
        target_allocation_pct = min(self.risk_cfg.max_risk_per_trade_pct * 3.0, fractional_kelly)
        target_usd = self.total_capital * target_allocation_pct
        return round(min(target_usd, self.available_capital), 2)

    def evaluate_decision(
        self,
        decision: TradeDecision,
        current_price: float,
        custom_sl_pct: Optional[float] = None,
        custom_tp_pct: Optional[float] = None,
    ) -> RiskVerdict:
        """Evaluates trade proposal against strict risk mandates with veto authority."""
        # 1. Check Emergency Circuit Breaker
        if self.emergency_halt:
            return self._veto(decision.pair, decision.action, "Trading halted by emergency circuit breaker.")

        if decision.action not in ["BUY", "SELL"]:
            return RiskVerdict(
                approved=False,
                pair=decision.pair,
                action=decision.action,
                allocated_usd=0.0,
                position_size_asset=0.0,
                stop_loss_price=0.0,
                take_profit_price=0.0,
                risk_reward_ratio=0.0,
                veto_reason="Non-actionable decision (HOLD or NO_TRADE).",
            )

        # 2. Portfolio Exposure Limit Check
        projected_exposure = self.active_exposure_usd + (self.total_capital * 0.05)
        if projected_exposure / self.total_capital > self.risk_cfg.max_portfolio_exposure_pct:
            return self._veto(
                decision.pair,
                decision.action,
                f"Maximum portfolio exposure ceiling ({self.risk_cfg.max_portfolio_exposure_pct:.0%}) reached.",
            )

        # 3. Calculate Stop Loss & Take Profit
        cand_sl = custom_sl_pct if custom_sl_pct is not None else getattr(decision, "custom_sl_pct", None)
        cand_tp = custom_tp_pct if custom_tp_pct is not None else getattr(decision, "custom_tp_pct", None)

        if cand_sl is not None and cand_tp is not None and (cand_tp / cand_sl) >= self.risk_cfg.min_risk_reward_ratio:
            sl_pct = cand_sl
            tp_pct = cand_tp
        else:
            sl_pct = self.risk_cfg.stop_loss_pct
            tp_pct = self.risk_cfg.take_profit_pct

        rr_ratio = tp_pct / sl_pct

        if rr_ratio < self.risk_cfg.min_risk_reward_ratio:
            return self._veto(
                decision.pair,
                decision.action,
                f"Risk/reward ratio ({rr_ratio:.2f}) below mandated threshold ({self.risk_cfg.min_risk_reward_ratio:.2f}).",
            )

        if decision.action == "BUY":
            stop_price = current_price * (1 - sl_pct)
            take_profit_price = current_price * (1 + tp_pct)
        else:
            stop_price = current_price * (1 + sl_pct)
            take_profit_price = current_price * (1 - tp_pct)

        # 4. Position Sizing
        allocated_usd = self.calculate_position_size(
            current_price=current_price,
            win_prob=decision.confidence,
            expected_win_loss_ratio=rr_ratio,
        )

        if allocated_usd < 15.0:  # Binance spot minimum order size
            return self._veto(
                decision.pair,
                decision.action,
                f"Calculated allocation (${allocated_usd:.2f}) below exchange minimum order size ($15).",
            )

        asset_qty = round(allocated_usd / current_price, 6)

        return RiskVerdict(
            approved=True,
            pair=decision.pair,
            action=decision.action,
            allocated_usd=allocated_usd,
            position_size_asset=asset_qty,
            stop_loss_price=round(stop_price, 2),
            take_profit_price=round(take_profit_price, 2),
            risk_reward_ratio=round(rr_ratio, 2),
            veto_reason=None,
        )

    def _veto(self, pair: str, action: str, reason: str) -> RiskVerdict:
        try:
            with self.db_manager.get_session() as session:
                ev = RiskEvent(
                    event_type="TRADE_VETO",
                    severity="warning",
                    reason=f"[{pair}] {action} vetoed: {reason}",
                    timestamp=datetime.now(timezone.utc),
                )
                session.add(ev)
        except Exception:
            pass

        return RiskVerdict(
            approved=False,
            pair=pair,
            action=action,
            allocated_usd=0.0,
            position_size_asset=0.0,
            stop_loss_price=0.0,
            take_profit_price=0.0,
            risk_reward_ratio=0.0,
            veto_reason=reason,
        )

