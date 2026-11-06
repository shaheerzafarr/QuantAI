# QuantAI: Operational Runbook & Disaster Recovery Protocol

**System Version:** 1.0.0-rc1  
**Target Exchange:** Binance Spot (`BTC/USDT`, `ETH/USDT`)  
**Standard Execution Mode:** Dry-Run / Paper Trading  

---

## 1. Quick Reference Command Cheat Sheet

### Terminal Status & Telemetry
```powershell
python -m quantai.cli status
```
*Outputs current portfolio balances, active exposure, circuit-breaker status, and recent decisions.*

### Starting the Autonomous 24/7 Trading Daemon
```powershell
python -m quantai.cli daemon
```
*Runs the continuous background loop polling Binance, running swarm deliberation, managing trailing stops, and recording simulated orders.*

### Launching FastAPI Server & Live UI Dashboard
```powershell
python -m quantai.cli api --port 8000
```
*Dashboard URL:* [http://localhost:8000/dashboard](http://localhost:8000/dashboard)  
*Prometheus Metrics URL:* [http://localhost:8000/metrics](http://localhost:8000/metrics)  
*OpenAPI Swagger Docs:* [http://localhost:8000/docs](http://localhost:8000/docs)

### Generating an Excel Paper Trading Audit
```powershell
python -m quantai.cli paper-audit --symbol BTC/USDT --candles 150 --output user_data/QuantAI_Paper_Trading_Audit.xlsx
```

### Running the 8-Strategy Benchmark Comparison
```powershell
python -m quantai.cli benchmark --candles 150
```

### Downloading Historical Data
```powershell
python -m quantai.cli download --symbol BTC/USDT --timeframe 5m --limit 500
```

### Running Freqtrade with QuantAI Extensions
```powershell
python -m quantai.cli freqtrade trade
```

---

## 2. Emergency Circuit Breaker & Incident Response

### Automatic Halt Triggers
The **Independent Risk Guardian** automatically freezes all trading upon:
1. **Daily Loss Breach:** Daily drawdown reaching or exceeding 2.0%.
2. **Cumulative Drawdown Breach:** Portfolio drawdown reaching or exceeding 6.0%.
3. **Data Stale / Feed Disconnect:** Orderbook spread anomalies or API disconnection exceeding 60 seconds.

### Manual Circuit Breaker Activation
1. **Via UI Dashboard:** Click the red **CIRCUIT BREAKER** button in the top right corner of the dashboard.
2. **Via REST API:**
   ```bash
   curl -X POST "http://localhost:8000/api/v1/risk/halt?reason=ManualOperatorOverride"
   ```

### Recovery & Unfreeze Procedure
Once a circuit breaker has been triggered, the system enters a fail-safe read-only state. To safely recover:
1. Review the incident log in the database:
   ```powershell
   python -c "from quantai.storage.db import get_db_manager; from quantai.storage.models import RiskEvent; mgr = get_db_manager(); s = mgr.get_session(); print([e.reason for e in s.query(RiskEvent).all()])"
   ```
2. Verify that open positions were closed safely or are properly hedged.
3. If market volatility has normalized and account equity is verified, restart the daemon process.

---

## 3. Upstream Freqtrade Synchronization

To keep the embedded Freqtrade codebase updated with official upstream releases:

```powershell
# 1. Fetch upstream changes
git fetch upstream

# 2. Inspect upstream updates without touching QuantAI modules
git log upstream/develop --oneline -n 10

# 3. Pull updates into the freqtrade/ directory if desired
cd freqtrade
git pull origin develop
cd ..
```

---

## 4. Controlled Live Deployment Gate (Phase 11 Checklist)

Live execution must never be enabled until all of the following conditions are met:

- [ ] **Forward Paper Observation:** At least 30–60 days of continuous forward paper observation logged.
- [ ] **Expectancy Validation:** Positive net expectancy maintained after accounting for realistic maker/taker fees and slippage.
- [ ] **Drawdown Compliance:** Maximum historical drawdown did not exceed 6.0% during paper observation.
- [ ] **Exchange API Key Safety:** API keys configured with **Spot Trading only**; withdrawal permissions must remain permanently disabled.
- [ ] **IP Whitelisting:** API keys restricted to dedicated server IP addresses on Binance.
- [ ] **Independent Risk Veto:** Verified that the risk guardian rejected invalid trade proposals under extreme simulated market events.

