# QuantAI: Autonomous Quantitative Intelligence & Cryptocurrency Trading Platform

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Architecture: Modular Monolith](https://img.shields.io/badge/architecture-modular%20monolith-success.svg)]()
[![Exchange: Binance Spot](https://img.shields.io/badge/exchange-binance%20spot-yellow.svg)]()
[![Execution Mode: Dry--Run Paper](https://img.shields.io/badge/execution-dry--run%20paper-purple.svg)]()

QuantAI is an institutional-grade quantitative research and autonomous trading ecosystem built to extend the open-source Freqtrade execution substrate. QuantAI integrates 16 specialized analytical and operational subsystems spanning on-chain whale intelligence, real-time order-flow dynamics, derivatives positioning, calibrated machine learning, a 12-agent research swarm, and an independent mathematical risk guardian.

---

## 🏛️ System Architecture

```text
quantai/
├── config/                 # Pydantic v2 settings, risk thresholds & exchange configs
├── storage/                # 30 domain tables, TimescaleDB & SQLite multi-engine ORM
├── ingestion/              # Binance REST/WS & Blockchain Ingestion Engine
├── intelligence/           # Domain Intelligence Engines
│   ├── whale/              # Wallet clustering, exchange flows & Smart Money scoring
│   ├── technical/          # Multi-timeframe vectorized indicator matrix (no lookahead)
│   ├── orderflow/          # Orderbook depth imbalance, CVD & absorption detection
│   ├── derivatives/        # Funding rate arbitrage, open interest & squeeze risks
│   ├── sentiment/          # News sentiment, event extraction & Fear & Greed index
│   ├── macro/              # DXY, Federal Reserve posture, BTC dominance
│   └── market_regime/      # Volatility & trend regime classifier
├── analytics/              # Hurst exponent, GARCH/EWMA volatility, VaR/CVaR
├── ml/                     # Purged & embargoed walk-forward CV, calibrated models
├── agents/                 # 12 specialist autonomous agents & swarm coordinator
├── research/               # Strategy library, Deflated Sharpe Ratio (DSR) & promotion
├── decision/               # Multi-signal fusion engine with transaction cost filters
├── risk/                   # Independent Risk Guardian & Fractional Kelly sizing
├── execution/              # Dry-run paper trading engine with slippage & fill tracking
└── api/                    # FastAPI REST endpoints & embedded glassmorphic UI
```

---

## 🚀 Quickstart Guide

### 1. Local Environment Setup

```bash
# 1. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -e .

# 3. Initialize SQLite database & storage domains
python -c "from quantai.storage.db import init_database; init_database()"
```

### 2. Launching QuantAI REST API & Dashboard

```bash
uvicorn quantai.api.main:app --host 0.0.0.0 --port 8000 --reload
```
Navigate to `http://localhost:8000/dashboard` in your browser to inspect live telemetry, trigger pipeline cycles, and observe multi-agent reasoning.

### 3. Docker Compose Deployment

```bash
docker-compose up -d
```
This provisions:
- **TimescaleDB** on port `5432`
- **Redis Cache** on port `6379`
- **QuantAI FastAPI Service** on port `8000`

---

## 🛡️ Independent Risk Governance

The **Independent Risk Guardian** operates completely decoupled from trading models and holds absolute veto power:
1. **Fractional Kelly Criterion:** Sizes positions based on empirical win probability and risk/reward.
2. **Exposure Ceiling:** Strict 50% max total capital deployment limit.
3. **Daily Loss Circuit Breaker:** Automatic trading halt upon 2% daily drawdown.
4. **Drawdown Emergency Halt:** Critical shutdown if cumulative drawdown reaches 6%.
5. **No Model Override:** Neither machine learning models nor agent consensus can bypass risk rules.

---

## 🧪 Running the Test Suite

```bash
pytest tests -v
```
