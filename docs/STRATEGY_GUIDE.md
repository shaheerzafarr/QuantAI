# QuantAI: Strategy Discovery & Quantitative Research Guide

---

## 1. Strategy Discovery Architecture

QuantAI implements a multi-paradigm quantitative strategy laboratory where multiple independent strategy families are evaluated, cross-validated, and promoted through a strict multi-stage lifecycle:

```text
Hypothesis Formulation
       │
       ▼
Historical Event Backtest (Realistic Fees & Slippage)
       │
       ▼
Purged Walk-Forward Cross-Validation (No Data Leakage)
       │
       ▼
Deflated Sharpe Ratio (DSR) Verification (Multi-testing Penalty)
       │
       ▼
Forward Paper Trading Forward Observation (30-60 Days)
       │
       ▼
Independent Risk Committee Approval (Production Deployment)
```

---

## 2. Core Strategy Families

### 1. Trend Following (`TrendFollowing_EMA`)
- **Core Hypothesis:** Sustained institutional accumulation creates persistent momentum across moving averages.
- **Entry Rules:** 
  - Short EMA (20) crosses above Intermediate EMA (50) with positive slope.
  - RSI (14) between 50 and 70 (confirming bullish momentum without overbought exhaustion).
  - Price above 200 EMA (macro structural trend filter).
- **Exit Rules:** 
  - EMA 20 crosses below EMA 50, or RSI exceeds 82 (momentum blow-off exhaustion).

### 2. Mean Reversion (`MeanReversion_BB`)
- **Core Hypothesis:** In ranging and compressed market regimes, extreme price deviations from the statistical mean represent mean-reverting liquidity grabs.
- **Entry Rules:**
  - Price punctures below the 20-period 2.0-standard-deviation lower Bollinger Band.
  - RSI (14) below 30 (oversold territory).
  - Market regime classified as `RANGING_COMPRESSION` or `VOLATILE_CHOP`.
- **Exit Rules:**
  - Price touches or crosses the 20-period moving average (mean target), or upper Bollinger Band.

### 3. Whale & Smart-Money Accumulation (`WhaleAccumulation_Follower`)
- **Core Hypothesis:** Large on-chain exchange outflows from high-conviction institutional wallets signal reduced spot circulating supply.
- **Entry Rules:**
  - On-chain transfer exceeding whale threshold ($500k for BTC, $250k for ETH).
  - Source classified as Exchange and Destination classified as Private/Institutional wallet (`EXCHANGE_OUTFLOW`).
  - Wallet Intelligence Score $\ge 70.0$.
  - Orderbook bid/ask depth imbalance confirms buyer absorption.

### 4. Multi-Agent & ML Fusion Strategy (`MultiAgent_ML_Fusion`)
- **Core Hypothesis:** Combining non-collinear analytical dimensions (on-chain whale flow + orderbook depth + derivatives funding + macroeconomic tailwinds + machine learning predictions) generates higher risk-adjusted expectancy than any single isolated indicator.
- **Entry Rules:**
  - Net swarm conviction $\ge 60\%$.
  - Adversarial Analyst fails to identify a high-probability bull/bear trap.
  - Machine learning model calibrated probability $\ge 62\%$.
  - Expected net edge exceeds roundtrip trading fees + market impact slippage.

---

## 3. Deflated Sharpe Ratio (DSR)

To guard against the fundamental flaw of quantitative finance—**data mining and selection bias under multiple testing**—QuantAI calculates Marcos López de Prado's Deflated Sharpe Ratio (DSR):

$$\text{DSR} = \frac{\widehat{\text{SR}} - \text{SR}^*}{\sqrt{\text{Var}(\widehat{\text{SR}})}}$$

Where:
- $\widehat{\text{SR}}$: Observed historical Sharpe ratio.
- $\text{SR}^*$: Expected maximum Sharpe ratio achievable purely by chance across $N$ trial attempts:
  $$\text{SR}^* \approx \frac{(1 - \gamma) Z^{-1}\left(1 - \frac{1}{N}\right) + \gamma Z^{-1}\left(1 - \frac{1}{N e}\right)}{\sqrt{T}}$$
- Any strategy with a negative DSR is automatically disqualified from promotion, regardless of its nominal historical returns.
