"""FastAPI Backend REST API for QuantAI."""

from datetime import datetime, timezone
import os
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, FileResponse
from pydantic import BaseModel

from quantai.config.settings import get_config
from quantai.monitoring.metrics import MetricsCollector
from quantai.ingestion.pipeline import IngestionPipeline
from quantai.intelligence.technical.feature_engine import TechnicalFeatureEngine
from quantai.intelligence.market_regime.detector import MarketRegimeDetector
from quantai.agents.swarm import MultiAgentSwarm
from quantai.decision.engine import DecisionFusionEngine
from quantai.risk.guardian import IndependentRiskGuardian
from quantai.execution.paper_engine import PaperExecutionEngine
from quantai.storage.db import get_db_manager, init_database
from quantai.storage.models import (
    TradeRecord,
    TradeDecisionRecord,
    WhaleEvent,
    RiskEvent,
    MarketCandle,
)

app = FastAPI(
    title="QuantAI Institutional Trading & Intelligence Platform API",
    version="1.0.0",
    description="Autonomous Quantitative Intelligence & Multi-Agent Cryptocurrency Engine",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize core services
init_database()
config = get_config()
ingestion_pipe = IngestionPipeline()
feature_engine = TechnicalFeatureEngine()
regime_detector = MarketRegimeDetector()
agent_swarm = MultiAgentSwarm()
decision_engine = DecisionFusionEngine()
risk_guardian = IndependentRiskGuardian(initial_capital_usd=100_000.0)
execution_engine = PaperExecutionEngine()


@app.get("/health")
def get_health() -> Dict[str, Any]:
    return {
        "status": "ONLINE",
        "app": config.app_name,
        "version": config.version,
        "mode": config.execution_mode.value,
        "ingestion": ingestion_pipe.get_health(),
        "emergency_halt": risk_guardian.emergency_halt,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/metrics", response_class=PlainTextResponse)
def get_prometheus_metrics() -> str:
    """Exposes real-time Prometheus telemetry metrics."""
    return MetricsCollector.format_prometheus_metrics(risk_guardian, execution_engine)


@app.get("/api/v1/portfolio")
def get_portfolio() -> Dict[str, Any]:
    return {
        "total_capital_usd": risk_guardian.total_capital,
        "available_capital_usd": risk_guardian.available_capital,
        "active_exposure_usd": risk_guardian.active_exposure_usd,
        "peak_capital_usd": risk_guardian.peak_capital,
        "daily_drawdown_pct": round(
            (risk_guardian.daily_start_capital - risk_guardian.total_capital)
            / risk_guardian.daily_start_capital,
            4,
        ),
        "total_drawdown_pct": round(
            (risk_guardian.peak_capital - risk_guardian.total_capital)
            / risk_guardian.peak_capital,
            4,
        ),
        "emergency_halt": risk_guardian.emergency_halt,
        "open_positions": [
            {
                "order_id": o.order_id,
                "pair": o.pair,
                "side": o.side,
                "amount": o.amount,
                "entry_price": o.entry_price,
                "stop_loss": o.stop_loss,
                "take_profit": o.take_profit,
            }
            for o in execution_engine.open_orders.values()
        ],
    }


@app.get("/api/v1/intelligence/whale")
def get_whale_events(limit: int = 20) -> List[Dict[str, Any]]:
    db_mgr = get_db_manager()
    with db_mgr.get_session() as session:
        events = (
            session.query(WhaleEvent)
            .order_by(WhaleEvent.timestamp.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": e.id,
                "event_type": e.event_type,
                "asset": e.asset,
                "amount": e.amount,
                "usd_value": e.usd_value,
                "source": e.source_wallet,
                "dest": e.dest_wallet,
                "signal_bias": e.signal_bias,
                "confidence": e.confidence,
                "timestamp": e.timestamp.isoformat(),
            }
            for e in events
        ]


@app.get("/api/v1/decisions")
def get_recent_decisions(limit: int = 20) -> List[Dict[str, Any]]:
    db_mgr = get_db_manager()
    with db_mgr.get_session() as session:
        decs = (
            session.query(TradeDecisionRecord)
            .order_by(TradeDecisionRecord.timestamp.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": d.id,
                "pair": d.pair,
                "timestamp": d.timestamp.isoformat(),
                "action": d.action,
                "confidence": d.confidence,
                "expected_return_bps": d.expected_return_bps,
                "risk_status": d.risk_status,
                "supporting_evidence": d.supporting_evidence,
                "contradictory_evidence": d.contradictory_evidence,
                "explanation": d.explanation,
            }
            for d in decs
        ]


@app.get("/api/v1/trades")
def get_trades(limit: int = 50) -> List[Dict[str, Any]]:
    db_mgr = get_db_manager()
    with db_mgr.get_session() as session:
        trades = (
            session.query(TradeRecord)
            .order_by(TradeRecord.open_time.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "order_id": t.order_id,
                "pair": t.pair,
                "side": t.side,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "amount": t.amount,
                "fee_paid": t.fee_paid,
                "realized_pnl": t.realized_pnl,
                "realized_pnl_pct": t.realized_pnl_pct,
                "open_time": t.open_time.isoformat(),
                "status": t.status,
            }
            for t in trades
        ]


@app.get("/api/v1/trades/live-ledger")
def get_live_ledger(pair: str = "ALL") -> List[Dict[str, Any]]:
    """Returns the forward marked trades ledger from the latest live Excel tracking sheet."""
    filename = "QuantAI_Live_Forward_Trades.xlsx"
    excel_path = os.path.abspath(os.path.join("user_data", filename))
    if not os.path.exists(excel_path):
        return []

    import openpyxl
    try:
        wb = openpyxl.load_workbook(excel_path, data_only=True)
    except Exception:
        return []

    if "Marked Trades Ledger" not in wb.sheetnames:
        return []

    ws = wb["Marked Trades Ledger"]
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) <= 1:
        return []

    headers = [str(h).strip().lower() if h else "" for h in rows[0]]
    header_idx = {h: i for i, h in enumerate(headers)}

    def get_val(row, key, default=None):
        idx = header_idx.get(key)
        if idx is not None and idx < len(row):
            return row[idx]
        return default

    trades = []
    for r in rows[1:]:
        if not r or not r[0]:
            continue
        try:
            trades.append({
                "trade_id": str(get_val(r, "trade id", "")),
                "status": str(get_val(r, "status", "")),
                "pair": str(get_val(r, "pair", "")),
                "side": str(get_val(r, "side", "")),
                "leverage": str(get_val(r, "leverage", "3x")),
                "margin_usd": float(get_val(r, "margin ($)", 0.0) or 0.0),
                "entry_time": str(get_val(r, "entry time", "")),
                "exit_time": str(get_val(r, "exit time", "")),
                "entry_price": float(get_val(r, "entry price ($)", 0.0) or 0.0),
                "exit_price": float(get_val(r, "current/exit price ($)", 0.0) or 0.0),
                "take_profit": float(get_val(r, "target tp ($)", 0.0) or 0.0),
                "stop_loss": float(get_val(r, "stop loss ($)", 0.0) or 0.0),
                "liquidation_price": float(get_val(r, "liq price ($)", 0.0) or 0.0),
                "risk_reward": float(get_val(r, "risk/reward", 0.0) or 0.0),
                "allocated_usd": float(get_val(r, "notional ($)", 0.0) or 0.0),
                "realized_pnl_usd": float(get_val(r, "realized pnl ($)", 0.0) or 0.0),
                "realized_pnl_pct": float(get_val(r, "roe (%)", 0.0) or 0.0),
                "exit_reason": str(get_val(r, "outcome / exit reason", "")),
                "thesis_confirmed": str(get_val(r, "thesis confirmed?", "")),
                "strategy_rationale": str(get_val(r, "strategy rationale", "")),
            })
        except Exception:
            pass
    return trades


@app.get("/api/v1/trades/download-excel")
def download_live_excel(pair: str = "ALL"):
    """Downloads the generated forward paper trading Excel ledger."""
    filename = "QuantAI_Live_Forward_Trades.xlsx"
    file_path = os.path.abspath(os.path.join("user_data", filename))
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Excel tracking file not yet generated. Run a cycle or replay first.")
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.post("/api/v1/pipeline/replay")
def trigger_replay(symbol: str = "BTC/USDT", candles: int = 120, timeframe: str = "15m") -> Dict[str, Any]:
    """Triggers sequential forward replay against real Binance candles and updates the Excel ledger."""
    from quantai.execution.live_observer import LiveMarketObserver
    filename = "QuantAI_Live_Forward_Trades.xlsx"
    excel_path = os.path.join("user_data", filename)
    observer = LiveMarketObserver(excel_path=excel_path)
    return observer.run_forward_replay(pair=symbol, total_bars=candles, interval=timeframe)


@app.post("/api/v1/risk/halt")
def trigger_halt(reason: str = "Manual operator override") -> Dict[str, Any]:
    risk_guardian.trigger_emergency_halt(reason)
    return {"status": "HALTED", "reason": reason}


@app.post("/api/v1/pipeline/cycle")
def execute_cycle(symbol: str = "BTC/USDT") -> Dict[str, Any]:
    """Runs one complete end-to-end cycle: Ingestion -> Indicators -> Swarm -> Fusion -> Risk -> Execution."""
    # 1. Sync Market Data
    candles = ingestion_pipe.sync_candles(symbol=symbol, timeframe="5m", limit=60)
    depth = ingestion_pipe.sync_orderbook(symbol=symbol)

    # 2. Build Features & Detect Regime
    db_mgr = get_db_manager()
    with db_mgr.get_session() as session:
        stored_candles = (
            session.query(MarketCandle)
            .filter(MarketCandle.pair == symbol)
            .order_by(MarketCandle.timestamp.asc())
            .all()
        )
        df = feature_engine.dataframe_from_candles(stored_candles)
    feat_df = feature_engine.compute_features(df)
    regime_state = regime_detector.detect_regime(feat_df)

    latest_close = float(feat_df.iloc[-1]["close"]) if len(feat_df) > 0 else 68000.0

    # 3. Multi-Agent Swarm Evaluation
    context = {
        "symbol": symbol,
        "features_df": feat_df,
        "regime": regime_state.regime.value,
        "hurst_exponent": 0.56,
        "price_zscore": 0.25,
        "spread": depth.spread,
        "estimated_slippage_bps": 2.5,
        "consensus_hint": "NEUTRAL",
    }
    agent_reports = agent_swarm.run_swarm(context)

    # 4. Decision Fusion
    decision = decision_engine.fuse_signals(
        symbol=symbol,
        agent_reports=agent_reports,
        estimated_slippage_bps=2.5,
    )

    # 5. Independent Risk Guardian
    verdict = risk_guardian.evaluate_decision(decision, latest_close)

    # 6. Execution Simulation
    executed_order = None
    if verdict.approved:
        executed_order = execution_engine.execute_order(verdict, latest_close)
        # Update active exposure
        risk_guardian.update_portfolio_state(
            current_total_usd=risk_guardian.total_capital,
            active_exposure_usd=risk_guardian.active_exposure_usd + verdict.allocated_usd,
        )

    return {
        "symbol": symbol,
        "latest_price": latest_close,
        "regime": regime_state.regime.value,
        "decision": {
            "action": decision.action,
            "confidence": decision.confidence,
            "expected_return_bps": decision.expected_return_bps,
            "explanation": decision.explanation,
        },
        "risk_verdict": {
            "approved": verdict.approved,
            "allocated_usd": verdict.allocated_usd,
            "stop_loss": verdict.stop_loss_price,
            "take_profit": verdict.take_profit_price,
            "veto_reason": verdict.veto_reason,
        },
        "order": (
            {
                "order_id": executed_order.order_id,
                "entry_price": executed_order.entry_price,
                "amount": executed_order.amount,
            }
            if executed_order
            else None
        ),
    }


@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
def render_dashboard() -> str:
    """Renders the self-contained QuantAI Institutional UI Dashboard."""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QuantAI - Autonomous Trading & Quantitative Intelligence Platform</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --bg-primary: #0a0e17;
            --bg-card: rgba(16, 24, 39, 0.75);
            --border: rgba(255, 255, 255, 0.08);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent-green: #10b981;
            --accent-red: #ef4444;
            --accent-blue: #3b82f6;
            --accent-purple: #8b5cf6;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        body { background: var(--bg-primary); color: var(--text-primary); min-height: 100vh; padding: 24px; }
        header { display: flex; justify-content: space-between; align-items: center; padding-bottom: 24px; border-bottom: 1px solid var(--border); }
        .logo-group { display: flex; align-items: center; gap: 12px; }
        .logo-badge { background: linear-gradient(135deg, var(--accent-blue), var(--accent-purple)); padding: 6px 12px; border-radius: 8px; font-weight: 700; font-size: 14px; }
        .status-pill { background: rgba(16, 185, 129, 0.15); color: var(--accent-green); padding: 4px 12px; border-radius: 20px; font-size: 13px; font-weight: 600; display: flex; align-items: center; gap: 6px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; margin-top: 24px; }
        .card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; backdrop-filter: blur(8px); }
        .card-title { font-size: 13px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px; font-weight: 600; }
        .metric-value { font-size: 28px; font-weight: 700; color: #fff; }
        .metric-sub { font-size: 13px; margin-top: 4px; color: var(--accent-green); }
        .btn { background: var(--accent-blue); color: white; border: none; padding: 8px 16px; border-radius: 8px; font-weight: 600; cursor: pointer; transition: 0.2s; }
        .btn:hover { opacity: 0.9; }
        .btn-danger { background: var(--accent-red); }
        .controls { display: flex; gap: 12px; margin-top: 24px; }
        table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 13px; }
        th { text-align: left; color: var(--text-secondary); padding: 8px; border-bottom: 1px solid var(--border); }
        td { padding: 10px 8px; border-bottom: 1px solid var(--border); }
        .badge { padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
        .badge-buy { background: rgba(16, 185, 129, 0.2); color: var(--accent-green); }
        .badge-sell { background: rgba(239, 68, 68, 0.2); color: var(--accent-red); }
        .badge-hold { background: rgba(148, 163, 184, 0.2); color: var(--text-secondary); }
    </style>
</head>
<body>
    <header>
        <div class="logo-group">
            <div class="logo-badge">QUANTAI 1.0</div>
            <h2>Autonomous Quantitative Intelligence Platform</h2>
        </div>
        <div style="display: flex; gap: 12px; align-items: center;">
            <div class="status-pill">● BINANCE SPOT DRY-RUN ACTIVE</div>
            <button class="btn btn-danger" onclick="triggerHalt()">CIRCUIT BREAKER</button>
        </div>
    </header>

    <div class="controls">
        <button class="btn" onclick="runCycle('BTC/USDT')">⚡ Run BTC/USDT Pipeline Cycle</button>
        <button class="btn" onclick="runCycle('ETH/USDT')">⚡ Run ETH/USDT Pipeline Cycle</button>
        <button class="btn" style="background: rgba(255,255,255,0.1);" onclick="refreshData()">🔄 Refresh Telemetry</button>
    </div>

    <div class="grid">
        <div class="card">
            <div class="card-title">Portfolio Capital</div>
            <div class="metric-value" id="totalCapital">$100,000.00</div>
            <div class="metric-sub" id="availableCapital">Available: $100,000.00</div>
        </div>
        <div class="card">
            <div class="card-title">Daily Drawdown</div>
            <div class="metric-value" id="dailyDrawdown">0.00%</div>
            <div class="metric-sub" style="color: var(--text-secondary);">Max Threshold: 2.00%</div>
        </div>
        <div class="card">
            <div class="card-title">Active Exposure</div>
            <div class="metric-value" id="activeExposure">$0.00</div>
            <div class="metric-sub" style="color: var(--text-secondary);">Cap: 50.00%</div>
        </div>
        <div class="card">
            <div class="card-title">Emergency Risk Status</div>
            <div class="metric-value" id="riskStatus" style="color: var(--accent-green); font-size: 20px;">NOMINAL</div>
            <div class="metric-sub" style="color: var(--text-secondary);">Kelly Sizing: 0.35x</div>
        </div>
    </div>

    <div style="display: grid; grid-template-columns: 2fr 1fr; gap: 20px; margin-top: 24px;">
        <div class="card">
            <div class="card-title">Live Strategy Decisions & Reasoning</div>
            <table id="decisionsTable">
                <thead>
                    <tr>
                        <th>Time</th>
                        <th>Asset</th>
                        <th>Action</th>
                        <th>Confidence</th>
                        <th>Expected Edge</th>
                        <th>Risk Status</th>
                    </tr>
                </thead>
                <tbody id="decisionsBody">
                    <tr><td colspan="6" style="text-align: center; color: var(--text-secondary);">Awaiting pipeline execution...</td></tr>
                </tbody>
            </table>
        </div>

        <div class="card">
            <div class="card-title">Whale & Smart-Money Intelligence</div>
            <div id="whaleFeed" style="display: flex; flex-direction: column; gap: 10px; margin-top: 12px; font-size: 13px;">
                <div style="color: var(--text-secondary);">Monitoring on-chain whale clusters...</div>
            </div>
        </div>
    </div>

    <script>
        async function refreshData() {
            try {
                const port = await fetch('/api/v1/portfolio').then(r => r.json());
                document.getElementById('totalCapital').innerText = '$' + port.total_capital_usd.toLocaleString(undefined, {minimumFractionDigits: 2});
                document.getElementById('availableCapital').innerText = 'Available: $' + port.available_capital_usd.toLocaleString(undefined, {minimumFractionDigits: 2});
                document.getElementById('activeExposure').innerText = '$' + port.active_exposure_usd.toLocaleString(undefined, {minimumFractionDigits: 2});
                document.getElementById('dailyDrawdown').innerText = (port.daily_drawdown_pct * 100).toFixed(2) + '%';
                
                if (port.emergency_halt) {
                    document.getElementById('riskStatus').innerText = 'HALTED';
                    document.getElementById('riskStatus').style.color = '#ef4444';
                }

                const decs = await fetch('/api/v1/decisions?limit=5').then(r => r.json());
                const tbody = document.getElementById('decisionsBody');
                if (decs && decs.length > 0) {
                    tbody.innerHTML = decs.map(d => `
                        <tr>
                            <td>${new Date(d.timestamp).toLocaleTimeString()}</td>
                            <td><strong>${d.pair}</strong></td>
                            <td><span class="badge ${d.action === 'BUY' ? 'badge-buy' : (d.action === 'SELL' ? 'badge-sell' : 'badge-hold')}">${d.action}</span></td>
                            <td>${(d.confidence * 100).toFixed(1)}%</td>
                            <td>+${d.expected_return_bps.toFixed(1)} bps</td>
                            <td>${d.risk_status}</td>
                        </tr>
                    `).join('');
                }

                const whales = await fetch('/api/v1/intelligence/whale?limit=4').then(r => r.json());
                const whaleFeed = document.getElementById('whaleFeed');
                if (whales && whales.length > 0) {
                    whaleFeed.innerHTML = whales.map(w => `
                        <div style="background: rgba(255,255,255,0.03); padding: 8px; border-radius: 6px; border-left: 3px solid ${w.signal_bias === 'BULLISH' ? '#10b981' : '#ef4444'};">
                            <div style="display: flex; justify-content: space-between;">
                                <strong>${w.event_type}</strong>
                                <span>$${(w.usd_value/1e6).toFixed(2)}M</span>
                            </div>
                            <div style="color: var(--text-secondary); font-size: 11px;">${w.asset} • Conf: ${(w.confidence*100).toFixed(0)}%</div>
                        </div>
                    `).join('');
                }
            } catch (err) {
                console.error("Telemetry fetch error:", err);
            }
        }

        async function runCycle(symbol) {
            try {
                const res = await fetch(`/api/v1/pipeline/cycle?symbol=${encodeURIComponent(symbol)}`, { method: 'POST' });
                const data = await res.json();
                alert(`Pipeline Cycle Finished for ${symbol}!\nAction: ${data.decision.action}\nPrice: $${data.latest_price}\nApproved: ${data.risk_verdict.approved}`);
                refreshData();
            } catch (err) {
                alert("Cycle error: " + err);
            }
        }

        async function triggerHalt() {
            if (confirm("Trigger Emergency Circuit Breaker Halt?")) {
                await fetch('/api/v1/risk/halt?reason=DashboardManualOverride', { method: 'POST' });
                refreshData();
            }
        }

        setInterval(refreshData, 5000);
        refreshData();
    </script>
</body>
</html>
    """
