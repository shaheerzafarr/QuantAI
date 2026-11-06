"""Autonomous Continuous Trading Daemon for QuantAI.

Orchestrates periodic market ingestion, multi-agent evaluation, risk checks,
and trade management across all configured pairs in a resilient background event loop.
"""

import asyncio
import logging
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from quantai.config.settings import get_config
from quantai.ingestion.pipeline import IngestionPipeline
from quantai.intelligence.technical.feature_engine import TechnicalFeatureEngine
from quantai.intelligence.market_regime.detector import MarketRegimeDetector
from quantai.agents.swarm import MultiAgentSwarm
from quantai.decision.engine import DecisionFusionEngine
from quantai.risk.guardian import IndependentRiskGuardian
from quantai.execution.paper_engine import PaperExecutionEngine
from quantai.storage.db import get_db_manager, init_database
from quantai.storage.models import MarketCandle, PortfolioSnapshot, SystemEvent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("quantai.daemon")


class QuantAIDaemon:
    """Continuous autonomous research and trading daemon."""

    def __init__(self, cycle_interval_seconds: float = 15.0):
        self.config = get_config()
        self.interval = cycle_interval_seconds
        self.running = False

        init_database()
        self.db_manager = get_db_manager()
        self.ingestion = IngestionPipeline()
        self.feature_engine = TechnicalFeatureEngine(primary_timeframe=self.config.exchange.primary_timeframe)
        self.regime_detector = MarketRegimeDetector()
        self.swarm = MultiAgentSwarm()
        self.decision_engine = DecisionFusionEngine()
        self.risk_guardian = IndependentRiskGuardian(initial_capital_usd=100_000.0)
        self.execution = PaperExecutionEngine()

    def stop(self):
        logger.info("Shutdown signal received. Stopping QuantAI Daemon gracefully...")
        self.running = False

    def process_pair(self, pair: str) -> Dict[str, Any]:
        """Executes a single cycle for an asset pair."""
        logger.info(f"Processing cycle for {pair}...")

        # 1. Sync Market Data
        candles = self.ingestion.sync_candles(symbol=pair, timeframe=self.config.exchange.primary_timeframe, limit=80)
        depth = self.ingestion.sync_orderbook(symbol=pair)

        # 2. Retrieve history and compute features
        with self.db_manager.get_session() as session:
            stored = (
                session.query(MarketCandle)
                .filter(MarketCandle.pair == pair)
                .order_by(MarketCandle.timestamp.asc())
                .all()
            )
            df = self.feature_engine.dataframe_from_candles(stored)

        feat_df = self.feature_engine.compute_features(df)
        regime_state = self.regime_detector.detect_regime(feat_df)
        latest_price = float(feat_df.iloc[-1]["close"]) if len(feat_df) > 0 else (depth.best_bid or 68000.0)

        # 3. Monitor and manage active open positions
        closed_positions = self.execution.evaluate_open_positions({pair: latest_price})
        for cp in closed_positions:
            logger.info(
                f"Position Closed: [{pair}] Order: {cp['order_id']} | Reason: {cp['reason']} | PnL: ${cp['realized_pnl']} ({cp['realized_pnl_pct']}%)"
            )

        # 4. Multi-Agent Swarm Intelligence Analysis
        context = {
            "symbol": pair,
            "features_df": feat_df,
            "regime": regime_state.regime.value,
            "hurst_exponent": 0.57,
            "price_zscore": float((latest_price - feat_df["close"].mean()) / (feat_df["close"].std() + 1e-10)) if len(feat_df) > 0 else 0.0,
            "spread": depth.spread,
            "estimated_slippage_bps": depth.spread / (latest_price + 1e-10) * 10_000,
            "consensus_hint": "NEUTRAL",
        }
        agent_reports = self.swarm.run_swarm(context)

        # 5. Signal and Decision Fusion
        decision = self.decision_engine.fuse_signals(
            symbol=pair,
            agent_reports=agent_reports,
            estimated_slippage_bps=context["estimated_slippage_bps"],
        )

        logger.info(
            f"[{pair}] Decision: {decision.action} | Confidence: {decision.confidence:.1%} | Net Edge: {decision.expected_return_bps:.1f} bps"
        )

        # 6. Independent Risk Guardian Evaluation
        verdict = self.risk_guardian.evaluate_decision(decision, latest_price)

        # 7. Paper Execution (if approved by Risk Guardian)
        order = None
        if verdict.approved:
            order = self.execution.execute_order(verdict, latest_price)
            logger.info(
                f"ORDER EXECUTED: [{pair}] {verdict.action} {order.amount:.4f} @ ${order.entry_price:,.2f} | SL: ${order.stop_loss:,.2f} | TP: ${order.take_profit:,.2f}"
            )
            self.risk_guardian.update_portfolio_state(
                current_total_usd=self.risk_guardian.total_capital,
                active_exposure_usd=self.risk_guardian.active_exposure_usd + verdict.allocated_usd,
            )
        elif verdict.veto_reason:
            logger.warning(f"[{pair}] Trade Vetoed by Risk Guardian: {verdict.veto_reason}")

        # 8. Record Portfolio Snapshot
        try:
            with self.db_manager.get_session() as session:
                snap = PortfolioSnapshot(
                    timestamp=datetime.now(timezone.utc),
                    total_balance_usd=self.risk_guardian.total_capital,
                    available_balance_usd=self.risk_guardian.available_capital,
                    active_exposure_usd=self.risk_guardian.active_exposure_usd,
                    unrealized_pnl_usd=0.0,
                    daily_drawdown_pct=(self.risk_guardian.daily_start_capital - self.risk_guardian.total_capital) / self.risk_guardian.daily_start_capital,
                    total_drawdown_pct=(self.risk_guardian.peak_capital - self.risk_guardian.total_capital) / self.risk_guardian.peak_capital,
                )
                session.add(snap)
        except Exception as e:
            logger.error(f"Failed to record portfolio snapshot: {e}")

        return {
            "pair": pair,
            "price": latest_price,
            "regime": regime_state.regime.value,
            "decision": decision.action,
            "approved": verdict.approved,
            "order": order.order_id if order else None,
        }

    async def run_loop(self):
        """Asynchronous execution loop."""
        self.running = True
        logger.info(f"QuantAI Daemon active. Pairs: {self.config.exchange.pairs}. Cycle: {self.interval}s")

        while self.running:
            cycle_start = time.time()
            for pair in self.config.exchange.pairs:
                try:
                    self.process_pair(pair)
                except Exception as e:
                    logger.error(f"Cycle execution error for {pair}: {e}", exc_info=True)

            elapsed = time.time() - cycle_start
            sleep_time = max(1.0, self.interval - elapsed)
            logger.info(f"Cycle completed in {elapsed:.2f}s. Sleeping for {sleep_time:.2f}s...")
            await asyncio.sleep(sleep_time)


def main():
    daemon = QuantAIDaemon(cycle_interval_seconds=15.0)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _sig_handler():
        daemon.stop()
        loop.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _sig_handler)
        except (NotImplementedError, AttributeError):
            # Windows signal handling fallback
            pass

    try:
        loop.run_until_complete(daemon.run_loop())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Stopping...")
    finally:
        daemon.stop()
        loop.close()
        logger.info("QuantAI Daemon terminated successfully.")


if __name__ == "__main__":
    main()
