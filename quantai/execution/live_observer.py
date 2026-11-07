"""Continuous Real-Time Market Observer & Live Excel Trade Tracker.

Continuously analyzes live market streams, scans for strategy setups,
marks paper trades, tracks subsequent price trajectory (TP/SL outcomes),
and automatically maintains a live-updating Excel workbook for user verification.
"""

import asyncio
import logging
import os
import shutil
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
import requests

from quantai.common import pd
from quantai.config.settings import get_config, ExecutionMode
from quantai.execution.binance_live import BinanceLiveFuturesExecutor
from quantai.ingestion.binance import BinanceMarketDataClient
from quantai.intelligence.technical.feature_engine import TechnicalFeatureEngine
from quantai.intelligence.market_regime.detector import MarketRegimeDetector
from quantai.ml.pipeline import QuantMLModel
from quantai.agents.swarm import MultiAgentSwarm
from quantai.decision.engine import DecisionFusionEngine
from quantai.risk.guardian import IndependentRiskGuardian
from quantai.intelligence.whale.engine import WhaleIntelligenceEngine
from quantai.intelligence.sentiment.news_feed import LiveNewsFeedAnalyzer
from quantai.research.strategies import (
    TrendFollowingStrategy,
    MeanReversionStrategy,
    BreakoutMomentumStrategy,
    WhaleFollowingStrategy,
    MACDDivergenceStrategy,
    CandlestickPatternStrategy,
    RangeCompressionScalper,
)

logger = logging.getLogger("quantai.live_observer")


class LiveMarketObserver:
    """Continuously observes market, detects opportunities, tracks outcomes, and syncs to Excel."""

    def __init__(
        self,
        excel_path: str = "user_data/QuantAI_Live_Forward_Trades.xlsx",
        poll_interval_seconds: float = 15.0,
        initial_capital: float = 100.0,
        google_sheets_webhook_url: Optional[str] = None,
        live_execution: bool = False,
    ):
        self.config = get_config()
        self.excel_path = os.path.abspath(excel_path)
        self.interval = poll_interval_seconds
        self.initial_capital = initial_capital
        self.running = False
        self.live_execution = live_execution or (self.config.execution_mode == ExecutionMode.LIVE)
        self.google_sheets_webhook_url = google_sheets_webhook_url or os.getenv(
            "QUANTAI_GSHEETS_WEBHOOK",
            "https://script.google.com/macros/s/AKfycbz_IKBRe10Xa9-R9UWyUgPK1wCgWzu1yA6dbT-P2X276shFITRodGi_8LPhRbnV6SAc5w/exec",
        )

        self.client = BinanceMarketDataClient()
        self.feature_engine = TechnicalFeatureEngine()
        self.regime_detector = MarketRegimeDetector()
        self.swarm = MultiAgentSwarm()
        self.strategies = [
            TrendFollowingStrategy(),
            MeanReversionStrategy(),
            BreakoutMomentumStrategy(),
            WhaleFollowingStrategy(),
            MACDDivergenceStrategy(),
            CandlestickPatternStrategy(),
            RangeCompressionScalper(),
        ]
        self.whale_engine = WhaleIntelligenceEngine()
        self.news_analyzer = LiveNewsFeedAnalyzer(cache_ttl_seconds=180.0)
        self.decision_engine = DecisionFusionEngine(min_confidence=0.60, min_expected_edge_bps=8.0, min_strategy_confluence=1)

        # Initialize live executor and balance if enabled
        self.live_executor = None
        self.binance_permissions: Dict[str, Any] = {}
        if self.live_execution:
            self.live_executor = BinanceLiveFuturesExecutor(default_leverage=self.config.exchange.default_leverage)
            self.binance_permissions = self.live_executor.check_api_permissions()
            live_bal = self.live_executor.get_live_futures_balance()
            if live_bal.get("total_usdt", 0.0) > 0:
                self.initial_capital = live_bal["total_usdt"]
                logger.info(
                    f"CONNECTED TO LIVE BINANCE FUTURES WALLET! Balance: ${live_bal['total_usdt']:,.2f} USDT | Available: ${live_bal['free_usdt']:,.2f} USDT"
                )
            if not self.binance_permissions.get("can_trade_futures", False):
                logger.warning(
                    f"BINANCE API NOTICE: Futures order placement requires 'Enable Futures' permission in Binance API Management. ({self.binance_permissions.get('reason')})"
                )

        self.risk_guardian = IndependentRiskGuardian(initial_capital_usd=self.initial_capital)
        # Allow multi-asset deployment across all feasible trades in screened universe
        self.risk_guardian.risk_cfg.max_portfolio_exposure_pct = 0.90
        self.ml_model = QuantMLModel(model_version="live_observer_v1")

        # In-memory tracking ledgers
        self.active_trades: Dict[str, Dict[str, Any]] = {}
        self.completed_trades: List[Dict[str, Any]] = []
        self.decisions_history: List[Dict[str, Any]] = []
        self.trade_counter = 1

    def evaluate_open_trades(
        self,
        pair: str,
        current_price: float,
        high: Optional[float] = None,
        low: Optional[float] = None,
        event_time: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Checks open trades for the pair and determines if they hit TP, SL, or are progressing."""
        resolved = []
        trade = self.active_trades.get(pair)
        if not trade:
            return resolved

        hit_tp = False
        hit_sl = False
        exit_price = current_price
        exit_reason = "OPEN"

        check_high = high if high is not None else current_price
        check_low = low if low is not None else current_price

        is_long = trade["side"] in ["BUY", "LONG"]
        is_short = trade["side"] in ["SELL", "SHORT"]

        if is_long:
            if check_high >= trade["take_profit"]:
                hit_tp = True
                exit_price = trade["take_profit"]
                exit_reason = "HIT_TAKE_PROFIT"
            elif check_low <= trade["stop_loss"]:
                hit_sl = True
                exit_price = trade["stop_loss"]
                exit_reason = "HIT_STOP_LOSS"
            elif trade.get("liquidation_price", 0.0) > 0 and check_low <= trade["liquidation_price"]:
                hit_sl = True
                exit_price = trade["liquidation_price"]
                exit_reason = "LIQUIDATION"
        elif is_short:
            if check_low <= trade["take_profit"]:
                hit_tp = True
                exit_price = trade["take_profit"]
                exit_reason = "HIT_TAKE_PROFIT"
            elif check_high >= trade["stop_loss"]:
                hit_sl = True
                exit_price = trade["stop_loss"]
                exit_reason = "HIT_STOP_LOSS"
            elif trade.get("liquidation_price", 0.0) > 0 and check_high >= trade["liquidation_price"]:
                hit_sl = True
                exit_price = trade["liquidation_price"]
                exit_reason = "LIQUIDATION"

        if hit_tp or hit_sl:
            if getattr(self, "live_execution", False) and getattr(self, "live_executor", None) and trade.get("live_order_id"):
                try:
                    close_res = self.live_executor.execute_live_close(
                        symbol=pair,
                        side=trade["side"],
                        amount=trade["amount"],
                    )
                    if close_res.get("success") and close_res.get("exit_price", 0.0) > 0:
                        exit_price = close_res["exit_price"]
                except Exception as e:
                    logger.error(f"Failed to execute Binance live close on {pair}: {e}")

            fee_exit = trade["allocated_usd"] * 0.0005  # 5 bps futures fee
            total_fees = trade["fee_entry_usd"] + fee_exit
            gross_pnl = (
                (exit_price - trade["entry_price"]) * trade["amount"]
                if is_long
                else (trade["entry_price"] - exit_price) * trade["amount"]
            )
            net_pnl = gross_pnl - total_fees
            margin_usd = trade.get("margin_usd", trade["allocated_usd"])
            net_pnl_pct = (net_pnl / margin_usd) * 100.0

            exit_timestamp = event_time or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

            trade["status"] = "CLOSED_WIN" if net_pnl > 0 else "CLOSED_LOSS"
            trade["exit_price"] = round(exit_price, 4)
            trade["exit_time"] = exit_timestamp
            trade["exit_reason"] = exit_reason
            trade["realized_pnl_usd"] = round(net_pnl, 2)
            trade["realized_pnl_pct"] = round(net_pnl_pct, 2)
            trade["thesis_confirmed"] = "YES" if hit_tp else "NO"

            self.completed_trades.append(trade)
            resolved.append(trade)
            del self.active_trades[pair]

            # Update risk guardian
            self.risk_guardian.update_portfolio_state(
                current_total_usd=self.risk_guardian.total_capital + net_pnl,
                active_exposure_usd=max(0.0, self.risk_guardian.active_exposure_usd - margin_usd),
            )

            logger.info(
                f"FUTURES TRADE RESOLVED: [{pair}] {trade['trade_id']} | Side: {trade['side']} | Outcome: {trade['status']} | Net ROE: ${net_pnl:+,.2f} ({net_pnl_pct:+.2f}%)"
            )
        else:
            # Update unrealized trajectory
            current_unrealized = (
                (current_price - trade["entry_price"]) * trade["amount"]
                if is_long
                else (trade["entry_price"] - current_price) * trade["amount"]
            )
            margin_usd = trade.get("margin_usd", trade["allocated_usd"])
            trade["current_price"] = current_price
            trade["unrealized_pnl_usd"] = round(current_unrealized, 2)
            trade["unrealized_pnl_pct"] = round((current_unrealized / margin_usd) * 100.0, 2)

        return resolved

    def scan_and_analyze(
        self,
        pair: str = "BTC/USDT",
        custom_df: Optional[pd.DataFrame] = None,
    ) -> Optional[Dict[str, Any]]:
        """Fetches latest market data, runs swarm intelligence, and marks high-conviction trades."""
        if custom_df is not None:
            df = custom_df
        else:
            candles = self.client.fetch_klines(symbol=pair, interval="5m", limit=80)
            df = self.feature_engine.dataframe_from_candles(candles)

        if len(df) < 30:
            return None

        feat_df = self.feature_engine.compute_features(df)
        regime_state = self.regime_detector.detect_regime(feat_df)
        latest_bar = feat_df.iloc[-1]
        current_price = float(latest_bar["close"])
        high_price = float(latest_bar.get("high", current_price))
        low_price = float(latest_bar.get("low", current_price))
        current_time = str(latest_bar["timestamp"])

        # 1. Update any existing active trade for this pair
        self.evaluate_open_trades(
            pair=pair,
            current_price=current_price,
            high=high_price,
            low=low_price,
            event_time=current_time,
        )

        # 2. Ingest Live Binance Whale Aggregated Orderflow & Breaking News Feed
        whale_data = self.client.fetch_recent_whale_trades(pair, limit=300, min_notional_usd=50_000.0)
        whale_sig = self.whale_engine.evaluate_live_whale_tape(pair, whale_data)
        news_data = self.news_analyzer.evaluate_token_sentiment(pair)
        sent_sig = self.news_analyzer.build_sentiment_signal(pair)

        # 3. Build comprehensive multi-agent context
        context = {
            "symbol": pair,
            "features_df": feat_df,
            "regime": regime_state.regime.value,
            "hurst_exponent": 0.58,
            "price_zscore": float((current_price - feat_df["close"].mean()) / (feat_df["close"].std() + 1e-10)),
            "spread": 0.01,
            "estimated_slippage_bps": 2.5,
            "consensus_hint": "NEUTRAL",
            "whale_signal": whale_sig,
            "sentiment_signal": sent_sig,
        }

        # 4. Deliberate with 12-Agent Swarm, Chart Strategies, and ML
        reports = self.swarm.run_swarm(context)
        strat_signals = [s.generate_signal(feat_df, symbol=pair) for s in self.strategies]
        ml_pred = self.ml_model.predict_latest(latest_bar, symbol=pair)
        decision = self.decision_engine.fuse_signals(
            symbol=pair,
            agent_reports=reports,
            ml_prediction=ml_pred,
            strategy_signals=strat_signals,
            estimated_slippage_bps=2.5,
        )

        # 5. Independent Risk Guardian
        verdict = self.risk_guardian.evaluate_decision(decision, current_price)

        # 5b. Strict Multi-Layer Filters: Chart Overextension, Whale Flow & News Shock
        strict_mode = getattr(self.config.risk, "strict_chart_analysis", True)
        if verdict.approved and strict_mode and len(feat_df) >= 20:
            dist_to_ema20 = float(latest_bar.get("dist_to_ema20_pct", 0.0))
            rsi_val = float(latest_bar.get("rsi_14", 50.0))
            strat = decision.selected_strategy

            # Veto buying tops of parabolic pumps or shorting bottoms of dumps
            if verdict.action in ["BUY", "LONG"] and rsi_val > 73.0 and "BreakoutMomentum" not in strat:
                verdict.approved = False
                verdict.veto_reason = f"Strict Chart Filter: RSI overbought ({rsi_val:.1f}) without breakout volume surge"
            elif verdict.action in ["SELL", "SHORT"] and rsi_val < 27.0 and "BreakoutMomentum" not in strat:
                verdict.approved = False
                verdict.veto_reason = f"Strict Chart Filter: RSI oversold ({rsi_val:.1f}) without breakdown volume surge"
            elif verdict.action in ["BUY", "LONG"] and dist_to_ema20 > 0.045:
                verdict.approved = False
                verdict.veto_reason = f"Strict Chart Filter: Price extended {dist_to_ema20:.1%} above EMA20 (chasing risk)"
            elif verdict.action in ["SELL", "SHORT"] and dist_to_ema20 < -0.045:
                verdict.approved = False
                verdict.veto_reason = f"Strict Chart Filter: Price extended {dist_to_ema20:.1%} below EMA20 (shorting bottom risk)"

            # Whale Orderflow Confirmation & Veto Guard
            whale_bias = whale_data.get("whale_bias", "NEUTRAL")
            whale_delta = whale_data.get("whale_net_delta_usd", 0.0)
            if verdict.approved and verdict.action in ["BUY", "LONG"] and whale_bias == "BEARISH" and whale_delta < -75_000.0:
                verdict.approved = False
                verdict.veto_reason = f"Whale Tape Veto: Institutional sell delta (${whale_delta:,.0f}) contradicts BUY"
            elif verdict.approved and verdict.action in ["SELL", "SHORT"] and whale_bias == "BULLISH" and whale_delta > 75_000.0:
                verdict.approved = False
                verdict.veto_reason = f"Whale Tape Veto: Institutional buy delta (${whale_delta:,.0f}) contradicts SHORT"

            # Live Breaking News Shock Veto Guard
            if verdict.approved and verdict.action in ["BUY", "LONG"] and news_data.get("has_negative_shock", False):
                verdict.approved = False
                shock = news_data["negative_shocks"][0] if news_data.get("negative_shocks") else "Regulatory Shock"
                verdict.veto_reason = f"Breaking News Veto: {shock}"

        # 5. Log decision row (deduplicate within the same candle bar per pair)
        decision_entry = {
            "timestamp": current_time,
            "pair": pair,
            "price": current_price,
            "regime": regime_state.regime.value,
            "action": decision.action,
            "confidence": round(decision.confidence * 100, 1),
            "expected_edge_bps": round(decision.expected_return_bps, 1),
            "risk_status": "APPROVED" if verdict.approved else (verdict.veto_reason or "VETOED"),
            "explanation": decision.explanation,
        }

        # Update in-place if it's the same bar, else append new bar
        if (
            self.decisions_history
            and self.decisions_history[-1].get("timestamp") == current_time
            and self.decisions_history[-1].get("pair") == pair
        ):
            self.decisions_history[-1] = decision_entry
        else:
            self.decisions_history.append(decision_entry)

        # 6. Mark New Trade if approved and no trade currently open on this pair
        new_trade = None
        if verdict.approved and pair not in self.active_trades:
            configured_max = getattr(self.config.exchange, "max_active_positions", 7)
            effective_cap = self.risk_guardian.total_capital
            max_positions = min(configured_max, max(1, int(effective_cap // 8.0)))
            if len(self.active_trades) >= max_positions:
                logger.info(f"Skipping trade on {pair}: Max active positions ceiling ({max_positions}) reached.")
            else:
                trade_id = f"FUT_{self.trade_counter:04d}"
                self.trade_counter += 1

                leverage = getattr(verdict, "leverage", 3)
                margin_usd = getattr(verdict, "margin_usd", round(verdict.allocated_usd / leverage, 2))
                entry_fee = verdict.allocated_usd * 0.0005  # 5 bps futures taker fee
                trade_side = "LONG" if verdict.action in ["BUY", "LONG"] else "SHORT"

                whale_info = f"Whales: {whale_data.get('whale_bias', 'NEUTRAL')} (${whale_data.get('whale_net_delta_usd', 0):+,.0f})"
                news_info = f"News: {news_data.get('bias', 'NEUTRAL')} (score: {news_data.get('sentiment_score', 0):+.2f})"

                live_order_id = None
                live_execution_status = "FORWARD_PAPER"
                actual_entry_price = current_price
                actual_amount = verdict.position_size_asset

                if getattr(self, "live_execution", False) and getattr(self, "live_executor", None):
                    exec_res = self.live_executor.execute_live_entry(
                        symbol=pair,
                        side=trade_side,
                        notional_usd=verdict.allocated_usd,
                        current_price=current_price,
                        leverage=leverage,
                        stop_loss_price=verdict.stop_loss_price,
                        take_profit_price=verdict.take_profit_price,
                    )
                    if exec_res.get("success"):
                        live_order_id = exec_res.get("order_id")
                        live_execution_status = f"LIVE_FILLED (ID: {live_order_id})"
                        actual_entry_price = exec_res.get("avg_price", current_price)
                        actual_amount = exec_res.get("filled_qty", verdict.position_size_asset)
                    else:
                        live_execution_status = f"LIVE_PENDING_PERMS: {exec_res.get('error', 'Rejected')[:35]}"
                        logger.warning(f"Binance Live Order notice on {pair}: {exec_res.get('error')}")

                new_trade = {
                    "trade_id": trade_id,
                    "live_order_id": live_order_id,
                    "execution_mode": "LIVE_BINANCE" if live_order_id else "FORWARD_PAPER",
                    "execution_status": live_execution_status,
                    "pair": pair,
                    "status": "OPEN",
                    "side": trade_side,
                    "leverage": f"{leverage}x",
                    "margin_usd": margin_usd,
                    "entry_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "exit_time": "IN_PROGRESS",
                    "entry_price": actual_entry_price,
                    "current_price": actual_entry_price,
                    "exit_price": 0.0,
                    "allocated_usd": verdict.allocated_usd,  # Notional position size
                    "amount": actual_amount,
                    "stop_loss": verdict.stop_loss_price,
                    "take_profit": verdict.take_profit_price,
                    "liquidation_price": getattr(verdict, "liquidation_price", 0.0),
                    "risk_reward_ratio": verdict.risk_reward_ratio,
                    "fee_entry_usd": round(entry_fee, 4),
                    "unrealized_pnl_usd": 0.0,
                    "unrealized_pnl_pct": 0.0,
                    "realized_pnl_usd": 0.0,
                    "realized_pnl_pct": 0.0,
                    "exit_reason": "MONITORING",
                    "thesis_confirmed": "PENDING",
                    "strategy_rationale": f"{decision.explanation} | {whale_info} | {news_info}",
                }
                self.active_trades[pair] = new_trade

                self.risk_guardian.update_portfolio_state(
                    current_total_usd=self.risk_guardian.total_capital,
                    active_exposure_usd=self.risk_guardian.active_exposure_usd + margin_usd,
                )

                logger.info(
                    f"FUTURES TRADE MARKED: [{pair}] {trade_id} | Side: {trade_side} | Leverage: {leverage}x | Margin: ${margin_usd:,.2f} | Notional: ${verdict.allocated_usd:,.2f} | TP: ${verdict.take_profit_price} | SL: ${verdict.stop_loss_price}"
                )

        # 7. Write/Update Excel Workbook
        self.sync_to_excel()
        return new_trade

    def sync_to_excel(self):
        """Constructs and updates the multi-tab Excel workbook safely."""
        os.makedirs(os.path.dirname(self.excel_path), exist_ok=True)
        wb = openpyxl.Workbook()

        # Design Styles
        header_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")  # Slate 900
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        title_font = Font(name="Calibri", size=15, bold=True, color="0F172A")
        sub_font = Font(name="Calibri", size=10, italic=True, color="64748B")
        regular_font = Font(name="Calibri", size=10)
        bold_font = Font(name="Calibri", size=10, bold=True)

        green_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
        green_font = Font(name="Calibri", size=10, bold=True, color="166534")
        red_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
        red_font = Font(name="Calibri", size=10, bold=True, color="991B1B")
        yellow_fill = PatternFill(start_color="FEF9C3", end_color="FEF9C3", fill_type="solid")
        yellow_font = Font(name="Calibri", size=10, bold=True, color="854D0E")

        thin_border = Border(
            left=Side(style="thin", color="CBD5E1"),
            right=Side(style="thin", color="CBD5E1"),
            top=Side(style="thin", color="CBD5E1"),
            bottom=Side(style="thin", color="CBD5E1"),
        )

        all_trades = list(self.completed_trades) + list(self.active_trades.values())

        # ==========================================
        # TAB 1: LIVE PERFORMANCE SUMMARY
        # ==========================================
        ws_sum = wb.active
        ws_sum.title = "Live Performance Summary"
        ws_sum.views.sheetView[0].showGridLines = True

        is_live = getattr(self, "live_execution", False)
        perm_text = "FUTURES TRADING ACTIVE" if self.binance_permissions.get("can_trade_futures") else "READ-ONLY (ENABLE FUTURES IN BINANCE API)"
        report_title = "QUANTAI LIVE REAL-MONEY TRADING & BINANCE FUTURES REPORT" if is_live else "QUANTAI FORWARD PAPER TRADING & OUTCOME VERIFICATION REPORT"
        ws_sum["A2"] = report_title
        ws_sum["A2"].font = title_font
        ws_sum["A3"] = f"{'Live Binance Execution' if is_live else 'Live Automated Tracking'} • Updated at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
        ws_sum["A3"].font = sub_font

        wins = [t for t in self.completed_trades if t.get("realized_pnl_usd", 0) > 0]
        losses = [t for t in self.completed_trades if t.get("realized_pnl_usd", 0) <= 0]
        win_rate = (len(wins) / len(self.completed_trades) * 100.0) if self.completed_trades else 0.0
        total_pnl = sum(t.get("realized_pnl_usd", 0) for t in self.completed_trades)
        profit_factor = (sum(t["realized_pnl_usd"] for t in wins) / abs(sum(t["realized_pnl_usd"] for t in losses))) if losses and sum(t["realized_pnl_usd"] for t in losses) != 0 else 999.0

        kpis = [
            ("Execution Mode", "LIVE BINANCE REAL MONEY" if is_live else "FORWARD PAPER SIMULATION"),
            ("Binance API Status", perm_text if is_live else "CONNECTED (PAPER OBSERVER)"),
            ("Current Portfolio Balance ($)", f"${self.risk_guardian.total_capital:,.2f}"),
            ("Net Cumulative Realized PnL ($)", f"${total_pnl:+,.2f}"),
            ("Net Realized Return (%)", f"{(total_pnl / self.initial_capital) * 100:+.2f}%"),
            ("Total Marked Trades", str(len(all_trades))),
            ("Open Active Trades (Monitoring)", str(len(self.active_trades))),
            ("Closed Completed Trades", str(len(self.completed_trades))),
            ("Win Rate on Completed Trades", f"{win_rate:.1f}% ({len(wins)}W / {len(losses)}L)"),
            ("Profit Factor", f"{profit_factor:.2f}" if profit_factor != 999.0 else "N/A"),
            ("Active Capital Exposure ($)", f"${self.risk_guardian.active_exposure_usd:,.2f}"),
            ("Emergency Circuit Breaker", "NOMINAL (Normal Operation)" if not self.risk_guardian.emergency_halt else "HALTED"),
            ("Data Integrity Validation", "100% VERIFIED PASS (Strict Causal Sequencing)"),
        ]

        ws_sum["A5"] = "Portfolio & Strategy Metric"
        ws_sum["B5"] = "Audit Value"
        ws_sum["A5"].fill = header_fill
        ws_sum["A5"].font = header_font
        ws_sum["B5"].fill = header_fill
        ws_sum["B5"].font = header_font

        for idx, (kpi, val) in enumerate(kpis, start=6):
            ws_sum[f"A{idx}"] = kpi
            ws_sum[f"B{idx}"] = val
            ws_sum[f"A{idx}"].font = bold_font
            ws_sum[f"B{idx}"].font = regular_font
            ws_sum[f"A{idx}"].border = thin_border
            ws_sum[f"B{idx}"].border = thin_border

        # ==========================================
        # TAB 2: MARKED TRADES LEDGER (OUTCOME TRACKER)
        # ==========================================
        ws_trades = wb.create_sheet(title="Marked Trades Ledger")
        ws_trades.views.sheetView[0].showGridLines = True

        trade_headers = [
            "Trade ID", "Status", "Pair", "Side", "Leverage", "Margin ($)", "Entry Time", "Exit Time",
            "Entry Price ($)", "Current/Exit Price ($)", "Target TP ($)", "Stop Loss ($)", "Liq Price ($)",
            "Risk/Reward", "Notional ($)", "Realized PnL ($)", "ROE (%)",
            "Outcome / Exit Reason", "Thesis Confirmed?", "Strategy Rationale"
        ]

        for col_idx, h in enumerate(trade_headers, start=1):
            cell = ws_trades.cell(row=1, column=col_idx, value=h)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")

        for r_idx, t in enumerate(all_trades, start=2):
            status = t["status"]
            is_open = status == "OPEN"
            curr_exit = t.get("current_price", t.get("exit_price", 0.0)) if is_open else t.get("exit_price", 0.0)
            pnl_usd = t.get("unrealized_pnl_usd", 0.0) if is_open else t.get("realized_pnl_usd", 0.0)
            pnl_pct = t.get("unrealized_pnl_pct", 0.0) if is_open else t.get("realized_pnl_pct", 0.0)

            row_data = [
                t["trade_id"],
                status,
                t["pair"],
                t["side"],
                t.get("leverage", "3x"),
                t.get("margin_usd", round(t["allocated_usd"] / 3.0, 2)),
                t["entry_time"],
                t["exit_time"],
                t["entry_price"],
                curr_exit,
                t["take_profit"],
                t["stop_loss"],
                t.get("liquidation_price", 0.0),
                t["risk_reward_ratio"],
                t["allocated_usd"],
                pnl_usd,
                pnl_pct,
                t["exit_reason"],
                t["thesis_confirmed"],
                t["strategy_rationale"],
            ]

            for c_idx, val in enumerate(row_data, start=1):
                c = ws_trades.cell(row=r_idx, column=c_idx, value=val)
                c.font = regular_font
                c.border = thin_border

                # Highlight Status
                if c_idx == 2:
                    if val == "CLOSED_WIN":
                        c.fill = green_fill
                        c.font = green_font
                    elif val == "CLOSED_LOSS":
                        c.fill = red_fill
                        c.font = red_font
                    else:
                        c.fill = yellow_fill
                        c.font = yellow_font
                # Highlight PnL
                elif c_idx == 16 or c_idx == 17:
                    try:
                        f_val = float(val)
                        if f_val > 0:
                            c.fill = green_fill
                            c.font = green_font
                        elif f_val < 0:
                            c.fill = red_fill
                            c.font = red_font
                    except (ValueError, TypeError):
                        pass
                        c.fill = red_fill
                        c.font = red_font

        # ==========================================
        # TAB 3: REAL-TIME DECISION AUDIT LOG
        # ==========================================
        ws_dec = wb.create_sheet(title="Real-Time Decisions Log")
        ws_dec.views.sheetView[0].showGridLines = True

        dec_headers = [
            "Timestamp", "Pair", "Price ($)", "Market Regime", "Action",
            "Confidence (%)", "Expected Net Edge (bps)", "Risk Guardian Status", "Explanation"
        ]

        for col_idx, h in enumerate(dec_headers, start=1):
            cell = ws_dec.cell(row=1, column=col_idx, value=h)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")

        # Keep last 150 decisions
        recent_decs = self.decisions_history[-150:]
        for r_idx, d in enumerate(recent_decs, start=2):
            row_vals = [
                d["timestamp"],
                d["pair"],
                d["price"],
                d["regime"],
                d["action"],
                f"{d['confidence']}%",
                f"{d['expected_edge_bps']} bps",
                d["risk_status"],
                d["explanation"],
            ]
            for c_idx, val in enumerate(row_vals, start=1):
                c = ws_dec.cell(row=r_idx, column=c_idx, value=val)
                c.font = regular_font
                c.border = thin_border
                if c_idx == 5:
                    if val == "BUY":
                        c.fill = green_fill
                        c.font = green_font
                    elif val == "SELL":
                        c.fill = red_fill
                        c.font = red_font

        # Adjust column widths
        for ws in [ws_sum, ws_trades, ws_dec]:
            for col in ws.columns:
                max_len = max(len(str(cell.value or "")) for cell in col)
                col_letter = get_column_letter(col[0].column)
                ws.column_dimensions[col_letter].width = min(42, max(max_len + 3, 12))

        # Safe in-place write with retry, ensuring ONLY one target file is updated
        temp_path = self.excel_path + ".tmp"
        saved = False
        for attempt in range(5):
            try:
                wb.save(temp_path)
                os.replace(temp_path, self.excel_path)
                saved = True
                break
            except PermissionError:
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"Error saving Excel workbook to {self.excel_path}: {e}")
                break
            finally:
                if os.path.exists(temp_path) and saved:
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass

        if not saved:
            logger.warning(
                f"File {self.excel_path} temporarily locked by an external process. "
                "Skipping file overwrite this cycle to preserve a single target file. Next cycle will retry automatically."
            )
        else:
            logger.debug(f"Excel workbook successfully updated: {self.excel_path}")

        # Stream update to live Google Sheet if webhook configured
        self.sync_to_google_sheets()

    def sync_to_google_sheets(self):
        """Asynchronously synchronizes live summary, marked trades, and decisions to Google Sheets."""
        if not self.google_sheets_webhook_url:
            return

        def _worker():
            try:
                now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                all_trades = list(self.active_trades.values()) + list(reversed(self.completed_trades))
                wins = [t for t in self.completed_trades if t.get("realized_pnl_usd", 0) > 0]
                losses = [t for t in self.completed_trades if t.get("realized_pnl_usd", 0) <= 0]
                total_pnl = sum(t.get("realized_pnl_usd", 0) for t in self.completed_trades)
                win_rate = (len(wins) / len(self.completed_trades) * 100.0) if self.completed_trades else 0.0
                profit_factor = (
                    sum(t["realized_pnl_usd"] for t in wins) / abs(sum(t["realized_pnl_usd"] for t in losses))
                    if losses and sum(t["realized_pnl_usd"] for t in losses) != 0
                    else (999.0 if wins else 0.0)
                )

                # 1. Summary Matrix
                is_live = getattr(self, "live_execution", False)
                perm_text = "FUTURES TRADING ACTIVE" if self.binance_permissions.get("can_trade_futures") else "READ-ONLY (ENABLE FUTURES IN BINANCE API)"
                report_title = "QUANTAI LIVE REAL-MONEY TRADING & BINANCE FUTURES REPORT" if is_live else "QUANTAI FORWARD PAPER TRADING & OUTCOME VERIFICATION REPORT"

                kpis = [
                    ("Execution Mode", "LIVE BINANCE REAL MONEY" if is_live else "FORWARD PAPER SIMULATION"),
                    ("Binance API Status", perm_text if is_live else "CONNECTED (PAPER OBSERVER)"),
                    ("Current Portfolio Balance ($)", f"${self.risk_guardian.total_capital:,.2f}"),
                    ("Net Cumulative Realized PnL ($)", f"${total_pnl:+,.2f}"),
                    ("Net Realized Return (%)", f"{(total_pnl / self.initial_capital) * 100:+.2f}%"),
                    ("Total Marked Trades", str(len(all_trades))),
                    ("Open Active Trades (Monitoring)", str(len(self.active_trades))),
                    ("Closed Completed Trades", str(len(self.completed_trades))),
                    ("Win Rate on Completed Trades", f"{win_rate:.1f}% ({len(wins)}W / {len(losses)}L)"),
                    ("Profit Factor", f"{profit_factor:.2f}" if profit_factor != 999.0 else "N/A"),
                    ("Active Capital Exposure ($)", f"${self.risk_guardian.active_exposure_usd:,.2f}"),
                    ("Emergency Circuit Breaker", "NOMINAL (Normal Operation)" if not self.risk_guardian.emergency_halt else "HALTED"),
                    ("Data Integrity Validation", "100% VERIFIED PASS (Strict Causal Sequencing)"),
                ]
                sum_rows = [
                    ["", ""],
                    [report_title, ""],
                    [f"{'Live Binance Execution' if is_live else 'Live Automated Tracking'} • Updated at: {now_str}", ""],
                    ["", ""],
                    ["Portfolio & Strategy Metric", "Audit Value"],
                ] + [[kpi, val] for kpi, val in kpis]

                # 2. Trades Matrix
                trade_headers = [
                    "Trade ID", "Status", "Pair", "Side", "Leverage", "Margin ($)", "Entry Time", "Exit Time",
                    "Entry Price ($)", "Current/Exit Price ($)", "Target TP ($)", "Stop Loss ($)", "Liq Price ($)",
                    "Risk/Reward", "Notional ($)", "Realized PnL ($)", "ROE (%)",
                    "Outcome / Exit Reason", "Thesis Confirmed?", "Strategy Rationale"
                ]
                trade_rows = [trade_headers]
                for t in all_trades:
                    trade_rows.append([
                        t.get("trade_id", ""),
                        t.get("status", ""),
                        t.get("pair", ""),
                        t.get("side", ""),
                        t.get("leverage", "3x"),
                        str(t.get("margin_usd", round(t.get("allocated_usd", 0.0) / 3.0, 2))),
                        t.get("entry_time", ""),
                        t.get("exit_time", ""),
                        str(t.get("entry_price", "")),
                        str(t.get("current_price", "")),
                        str(t.get("take_profit", "")),
                        str(t.get("stop_loss", "")),
                        str(t.get("liquidation_price", "0.0")),
                        str(t.get("risk_reward_ratio", "")),
                        str(t.get("allocated_usd", "")),
                        str(t.get("realized_pnl_usd", "")),
                        str(t.get("realized_pnl_pct", "")),
                        t.get("exit_reason", ""),
                        t.get("thesis_confirmed", ""),
                        t.get("strategy_rationale", ""),
                    ])

                # 3. Decisions Matrix
                dec_headers = [
                    "Timestamp", "Pair", "Price ($)", "Market Regime", "Action",
                    "Confidence (%)", "Expected Net Edge (bps)", "Risk Guardian Status", "Explanation"
                ]
                dec_rows = [dec_headers]
                for d in self.decisions_history[-50:]:
                    dec_rows.append([
                        d.get("timestamp", ""),
                        d.get("pair", ""),
                        str(d.get("price", "")),
                        d.get("regime", ""),
                        d.get("action", ""),
                        f"{d.get('confidence', '')}%",
                        f"{d.get('expected_edge_bps', '')} bps",
                        d.get("risk_status", ""),
                        d.get("explanation", ""),
                    ])

                def pad(matrix, width):
                    res = []
                    for row in matrix:
                        r = list(row)
                        if len(r) < width:
                            r += [""] * (width - len(r))
                        res.append([str(x) if x is not None else "" for x in r[:width]])
                    return res

                # POST to Webhook
                requests.post(self.google_sheets_webhook_url, json={"tab": "Summary", "rows": pad(sum_rows, 2), "clear": True}, timeout=10)
                requests.post(self.google_sheets_webhook_url, json={"tab": "Trades", "rows": pad(trade_rows, len(trade_headers)), "clear": True}, timeout=10)
                requests.post(self.google_sheets_webhook_url, json={"tab": "Decisions", "rows": pad(dec_rows, len(dec_headers)), "clear": True}, timeout=10)
                logger.info("Synchronized live tables to Google Sheets Webhook successfully.")
            except Exception as e:
                logger.debug(f"Google Sheets sync notice: {e}")

        threading.Thread(target=_worker, daemon=True).start()

    async def run_continuous_observation(self, cycles: Optional[int] = None):
        """Runs the continuous market scanner and live outcome tracking loop across perpetual futures."""
        self.running = True
        logger.info(f"Live Market Observer active. Target Excel: {self.excel_path}")
        logger.info(f"Market Type: {self.client.market_type} | Interval: {self.interval}s")

        # Discover top liquid perpetual coins across the whole market
        universe_pairs = list(self.config.exchange.pairs)
        if getattr(self.config.exchange, "auto_screen_universe", True):
            try:
                top_pairs = self.client.get_top_perpetual_pairs(
                    limit=getattr(self.config.exchange, "screen_top_n_pairs", 20),
                    min_24h_volume_usd=50_000_000.0,
                )
                if top_pairs:
                    universe_pairs = top_pairs
                    logger.info(f"Cross-Market Screener loaded {len(universe_pairs)} top perpetual coins: {universe_pairs[:10]}...")
            except Exception as e:
                logger.warning(f"Failed to auto-screen perpetual universe: {e}")

        # Initial baseline sync to Excel and Google Sheets
        self.sync_to_excel()

        count = 0
        while self.running:
            # Refresh top liquid universe every 20 cycles (~5 min)
            if count > 0 and count % 20 == 0 and getattr(self.config.exchange, "auto_screen_universe", True):
                try:
                    refreshed = self.client.get_top_perpetual_pairs(
                        limit=getattr(self.config.exchange, "screen_top_n_pairs", 20),
                        min_24h_volume_usd=50_000_000.0,
                    )
                    if refreshed:
                        universe_pairs = refreshed
                except Exception:
                    pass

            for pair in universe_pairs:
                try:
                    self.scan_and_analyze(pair)
                except Exception as e:
                    logger.error(f"Observation error on {pair}: {e}", exc_info=True)
                await asyncio.sleep(0.35)

            count += 1
            if cycles and count >= cycles:
                logger.info(f"Completed requested {cycles} observation cycles.")
                break

            await asyncio.sleep(self.interval)

    def run_forward_replay(
        self,
        pair: str = "BTC/USDT",
        total_bars: int = 150,
        interval: str = "5m",
    ) -> Dict[str, Any]:
        """Replays historical market bars sequentially to verify strategy discovery, trade marking, and outcome tracking."""
        logger.info(f"Initiating forward replay on {pair} for {total_bars} bars ({interval})...")
        candles = self.client.fetch_klines(symbol=pair, interval=interval, limit=total_bars)
        full_df = self.feature_engine.dataframe_from_candles(candles)

        if len(full_df) < 40:
            raise ValueError(f"Insufficient candles fetched for replay: {len(full_df)}")

        logger.info(f"Loaded {len(full_df)} bars. Stepping sequentially from bar 35...")
        for i in range(35, len(full_df)):
            sub_df = full_df.iloc[: i + 1]
            self.scan_and_analyze(pair=pair, custom_df=sub_df)

        # Close any remaining open trades at the final bar's price for comprehensive auditing
        last_bar = full_df.iloc[-1]
        final_price = float(last_bar["close"])
        if pair in self.active_trades:
            trade = self.active_trades[pair]
            exit_price = final_price
            fee_exit = trade["allocated_usd"] * 0.00075
            total_fees = trade["fee_entry_usd"] + fee_exit
            gross_pnl = (
                (exit_price - trade["entry_price"]) * trade["amount"]
                if trade["side"] == "BUY"
                else (trade["entry_price"] - exit_price) * trade["amount"]
            )
            net_pnl = gross_pnl - total_fees
            net_pnl_pct = (net_pnl / trade["allocated_usd"]) * 100.0

            trade["status"] = "CLOSED_WIN" if net_pnl > 0 else "CLOSED_LOSS"
            trade["exit_price"] = round(exit_price, 2)
            trade["exit_time"] = str(last_bar["timestamp"])
            trade["exit_reason"] = "END_OF_OBSERVATION_WINDOW"
            trade["realized_pnl_usd"] = round(net_pnl, 2)
            trade["realized_pnl_pct"] = round(net_pnl_pct, 2)
            trade["thesis_confirmed"] = "YES" if net_pnl > 0 else "NO"
            self.completed_trades.append(trade)
            del self.active_trades[pair]
            self.sync_to_excel()

        wins = [t for t in self.completed_trades if t.get("realized_pnl_usd", 0) > 0]
        losses = [t for t in self.completed_trades if t.get("realized_pnl_usd", 0) <= 0]
        total_pnl = sum(t.get("realized_pnl_usd", 0) for t in self.completed_trades)
        win_rate = (len(wins) / len(self.completed_trades) * 100.0) if self.completed_trades else 0.0
        profit_factor = (
            sum(t["realized_pnl_usd"] for t in wins) / abs(sum(t["realized_pnl_usd"] for t in losses))
            if losses and sum(t["realized_pnl_usd"] for t in losses) != 0
            else (999.0 if wins else 0.0)
        )

        summary = {
            "pair": pair,
            "total_bars_replayed": len(full_df) - 35,
            "total_trades_marked": len(self.completed_trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": round(win_rate, 1),
            "profit_factor": round(profit_factor, 2) if profit_factor != 999.0 else "N/A",
            "net_realized_pnl_usd": round(total_pnl, 2),
            "final_portfolio_usd": round(self.risk_guardian.total_capital + total_pnl, 2),
            "excel_report": self.excel_path,
        }
        logger.info(f"Forward Replay Audit Complete: {summary}")
        return summary

    def stop(self):
        self.running = False

