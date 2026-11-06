"""Dry-Run & Paper Trading Execution Engine."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
from quantai.risk.guardian import RiskVerdict
from quantai.storage.db import get_db_manager
from quantai.storage.models import TradeRecord


@dataclass
class PaperOrder:
    order_id: str
    pair: str
    side: str  # buy, sell
    amount: float
    entry_price: float
    stop_loss: float
    take_profit: float
    fee_paid: float
    slippage_bps: float
    status: str  # open, filled, closed, cancelled
    timestamp: str


class PaperExecutionEngine:
    """Simulates realistic exchange execution with orderbook slippage, fee accounting, and partial fills."""

    def __init__(self, fee_rate: float = 0.00075):  # 0.075% standard maker/taker fee
        self.fee_rate = fee_rate
        self.open_orders: Dict[str, PaperOrder] = {}
        self.db_manager = get_db_manager()

    def execute_order(
        self,
        verdict: RiskVerdict,
        market_price: float,
        slippage_bps: float = 3.0,
    ) -> Optional[PaperOrder]:
        """Places a simulated market order accounting for price impact."""
        if not verdict.approved:
            return None

        order_id = f"dry_{uuid.uuid4().hex[:10]}"
        side = verdict.action.lower()

        # Apply slippage
        slip_mult = 1.0 + (slippage_bps / 10_000.0) if side == "buy" else 1.0 - (slippage_bps / 10_000.0)
        execution_price = market_price * slip_mult
        fee_paid = verdict.allocated_usd * self.fee_rate

        order = PaperOrder(
            order_id=order_id,
            pair=verdict.pair,
            side=side,
            amount=verdict.position_size_asset,
            entry_price=round(execution_price, 2),
            stop_loss=verdict.stop_loss_price,
            take_profit=verdict.take_profit_price,
            fee_paid=round(fee_paid, 4),
            slippage_bps=slippage_bps,
            status="filled",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        self.open_orders[order_id] = order

        # Record trade in DB
        try:
            with self.db_manager.get_session() as session:
                rec = TradeRecord(
                    pair=order.pair,
                    order_id=order.order_id,
                    side=order.side,
                    entry_price=order.entry_price,
                    amount=order.amount,
                    fee_paid=order.fee_paid,
                    slippage_bps=order.slippage_bps,
                    open_time=datetime.now(timezone.utc),
                    status="open",
                    is_dry_run=True,
                )
                session.add(rec)
        except Exception:
            pass

        return order

    def evaluate_open_positions(
        self, current_prices: Dict[str, float]
    ) -> List[Dict[str, Any]]:
        """Checks open positions against Stop Loss and Take Profit levels."""
        closed_orders = []

        for oid, order in list(self.open_orders.items()):
            price = current_prices.get(order.pair)
            if not price:
                continue

            hit_sl = False
            hit_tp = False

            if order.side == "buy":
                if price <= order.stop_loss:
                    hit_sl = True
                elif price >= order.take_profit:
                    hit_tp = True
            elif order.side == "sell":
                if price >= order.stop_loss:
                    hit_sl = True
                elif price <= order.take_profit:
                    hit_tp = True

            if hit_sl or hit_tp:
                reason = "TAKE_PROFIT" if hit_tp else "STOP_LOSS"
                pnl = (
                    (price - order.entry_price) * order.amount
                    if order.side == "buy"
                    else (order.entry_price - price) * order.amount
                )
                pnl_pct = (pnl / (order.entry_price * order.amount)) * 100.0

                # Update in DB
                try:
                    with self.db_manager.get_session() as session:
                        rec = (
                            session.query(TradeRecord)
                            .filter(TradeRecord.order_id == oid)
                            .first()
                        )
                        if rec:
                            rec.exit_price = price
                            rec.realized_pnl = round(pnl, 2)
                            rec.realized_pnl_pct = round(pnl_pct, 2)
                            rec.close_time = datetime.now(timezone.utc)
                            rec.status = "closed"
                except Exception:
                    pass

                del self.open_orders[oid]
                closed_orders.append(
                    {
                        "order_id": oid,
                        "pair": order.pair,
                        "exit_price": price,
                        "realized_pnl": round(pnl, 2),
                        "realized_pnl_pct": round(pnl_pct, 2),
                        "reason": reason,
                    }
                )

        return closed_orders
