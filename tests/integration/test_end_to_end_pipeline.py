"""Integration Test: Full End-to-End Cycle across All 16 Modules."""

import pytest
from quantai.storage.db import init_database
from quantai.ingestion.pipeline import IngestionPipeline
from quantai.intelligence.technical.feature_engine import TechnicalFeatureEngine
from quantai.intelligence.market_regime.detector import MarketRegimeDetector
from quantai.agents.swarm import MultiAgentSwarm
from quantai.decision.engine import DecisionFusionEngine
from quantai.risk.guardian import IndependentRiskGuardian
from quantai.execution.paper_engine import PaperExecutionEngine


def test_full_autonomous_cycle():
    # 1. Initialize Storage
    init_database()

    # 2. Ingestion
    ingestion = IngestionPipeline()
    candles = ingestion.sync_candles(symbol="BTC/USDT", timeframe="5m", limit=50)
    assert len(candles) >= 10
    depth = ingestion.sync_orderbook(symbol="BTC/USDT")
    assert depth.best_bid > 0

    # 3. Features & Regime
    feature_engine = TechnicalFeatureEngine()
    df = feature_engine.dataframe_from_candles(
        [
            type(
                "MockCandle",
                (),
                {
                    "timestamp": c.event_time,
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume,
                },
            )()
            for c in candles
        ]
    )
    feat_df = feature_engine.compute_features(df)
    regime_detector = MarketRegimeDetector()
    regime_state = regime_detector.detect_regime(feat_df)
    assert regime_state.regime is not None

    # 4. Multi-Agent Swarm
    swarm = MultiAgentSwarm()
    context = {
        "symbol": "BTC/USDT",
        "features_df": feat_df,
        "regime": regime_state.regime.value,
        "hurst_exponent": 0.55,
        "price_zscore": 0.1,
        "spread": depth.spread,
        "estimated_slippage_bps": 2.5,
    }
    agent_reports = swarm.run_swarm(context)
    assert len(agent_reports) == 12

    # 5. Decision Fusion
    fusion = DecisionFusionEngine()
    decision = fusion.fuse_signals(
        symbol="BTC/USDT",
        agent_reports=agent_reports,
        estimated_slippage_bps=2.5,
    )
    assert decision.action in ["BUY", "SELL", "HOLD", "NO_TRADE"]

    # 6. Independent Risk Guardian
    risk_guardian = IndependentRiskGuardian(initial_capital_usd=100_000.0)
    latest_price = float(feat_df.iloc[-1]["close"])
    verdict = risk_guardian.evaluate_decision(decision, latest_price)
    assert verdict is not None

    # 7. Paper Execution
    exec_engine = PaperExecutionEngine()
    if verdict.approved:
        order = exec_engine.execute_order(verdict, latest_price)
        assert order is not None
        assert order.status == "filled"

