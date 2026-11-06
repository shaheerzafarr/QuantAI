"""QuantAI Freqtrade Strategy Integration Adapter.

Provides seamless bidirectional compatibility between Freqtrade's lifecycle hooks
and the proprietary QuantAI Multi-Agent & Machine Learning Decision Engine.
"""

from typing import Dict, Optional
import numpy as np
from quantai.common import pd

# Try importing Freqtrade base classes; fall back gracefully if running in standalone QuantAI mode
try:
    from freqtrade.strategy import IStrategy
    from freqtrade.strategy import IntParameter, DecimalParameter
except ImportError:
    class IStrategy:
        """Standalone mock of Freqtrade IStrategy interface."""
        minimal_roi = {"0": 0.04, "30": 0.02, "60": 0.01}
        stoploss = -0.015
        timeframe = "5m"

from quantai.intelligence.technical.feature_engine import TechnicalFeatureEngine
from quantai.agents.swarm import MultiAgentSwarm
from quantai.decision.engine import DecisionFusionEngine
from quantai.risk.guardian import IndependentRiskGuardian


class QuantAIStrategy(IStrategy):
    """
    QuantAI Institutional Autonomous Trading Strategy.
    Integrates 16 modular subsystems into Freqtrade execution framework.
    """

    INTERFACE_VERSION = 3
    timeframe = "5m"
    can_short = False  # Binance Spot execution

    # Risk Controls mapped into Freqtrade
    minimal_roi = {
        "0": 0.035,   # 3.5% take profit
        "60": 0.02,
        "120": 0.01,
    }
    stoploss = -0.015  # -1.5% stop loss
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset_pnl = 0.02
    trailing_only_offset_is_reached = True

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config) if hasattr(super(), "__init__") else None
        self.feature_engine = TechnicalFeatureEngine(primary_timeframe=self.timeframe)
        self.agent_swarm = MultiAgentSwarm()
        self.decision_engine = DecisionFusionEngine()
        self.risk_guardian = IndependentRiskGuardian()

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """Computes full multi-timeframe feature matrix without lookahead bias."""
        return self.feature_engine.compute_features(dataframe)

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """
        Executes Multi-Agent Swarm, ML Calibrated Probability, and Independent Risk Veto
        to set deterministic 'enter_long' trigger flags.
        """
        dataframe["enter_long"] = 0
        dataframe["enter_tag"] = ""

        if len(dataframe) < 35:
            return dataframe

        pair = metadata.get("pair", "BTC/USDT")
        latest_row = dataframe.iloc[-1]
        current_price = float(latest_row["close"])

        # Construct Agent Analytical Context
        context = {
            "symbol": pair,
            "features_df": dataframe,
            "hurst_exponent": 0.58,  # persistent trend
            "price_zscore": float((latest_row["close"] - dataframe["close"].mean()) / (dataframe["close"].std() + 1e-10)),
            "spread": 0.01,
            "estimated_slippage_bps": 2.5,
        }

        # Run Multi-Agent Intelligence Swarm
        agent_reports = self.agent_swarm.run_swarm(context)

        # Run Decision Fusion
        decision = self.decision_engine.fuse_signals(
            symbol=pair,
            agent_reports=agent_reports,
            estimated_slippage_bps=2.5,
        )

        # Independent Risk Guardian Evaluation
        verdict = self.risk_guardian.evaluate_decision(decision, current_price)

        if verdict.approved and verdict.action == "BUY":
            dataframe.iloc[-1, dataframe.columns.get_loc("enter_long")] = 1
            dataframe.iloc[-1, dataframe.columns.get_loc("enter_tag")] = f"QuantAI_Conf_{decision.confidence:.2f}"

        return dataframe

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """Sets deterministic exit triggers based on risk parameters or bearish breakdown."""
        dataframe["exit_long"] = 0
        dataframe["exit_tag"] = ""

        if len(dataframe) < 30:
            return dataframe

        latest_row = dataframe.iloc[-1]
        rsi = latest_row.get("rsi_14", 50.0)

        # Emergency momentum exhaustion exit trigger
        if rsi > 82.0:
            dataframe.iloc[-1, dataframe.columns.get_loc("exit_long")] = 1
            dataframe.iloc[-1, dataframe.columns.get_loc("exit_tag")] = "RSI_Overextended_Exit"

        return dataframe
