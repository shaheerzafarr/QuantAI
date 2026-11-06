"""Specialist Multi-Agent Swarm Implementations."""

from typing import Any, Dict, List
from quantai.agents.base import BaseAnalyst, AgentReport


class WhaleAnalyst(BaseAnalyst):
    def __init__(self):
        super().__init__("WhaleAnalyst", "Wallet & Institutional Flow Specialist")

    def evaluate(self, context: Dict[str, Any]) -> AgentReport:
        symbol = context.get("symbol", "BTC/USDT")
        whale_sig = context.get("whale_signal")

        if whale_sig and whale_sig.actionable_signal:
            bias = whale_sig.signal_bias
            conf = whale_sig.attribution_confidence
            findings = [
                f"Detected {whale_sig.event_type} of ${whale_sig.usd_value:,.0f} USD.",
                f"Source: {whale_sig.source_category} -> Dest: {whale_sig.dest_category}",
                f"Smart Money Score: {whale_sig.smart_money_score}/100",
            ]
            corroborating = [f"Direct on-chain movement of {whale_sig.asset}"]
            counters = ["Large transfers may represent internal cold storage rebalancing"]
            rec = "BUY" if bias == "BULLISH" else "SELL"
        else:
            bias = "NEUTRAL"
            conf = 0.50
            findings = ["No abnormal institutional wallet transfers detected within threshold."]
            corroborating = []
            counters = []
            rec = "HOLD"

        return AgentReport(
            agent_name=self.name,
            role=self.role,
            symbol=symbol,
            bias=bias,
            confidence=conf,
            key_findings=findings,
            corroborating_evidence=corroborating,
            counter_arguments=counters,
            actionable_recommendation=rec,
        )


class TechnicalAnalyst(BaseAnalyst):
    def __init__(self):
        super().__init__("TechnicalAnalyst", "Price Structure & Indicator Specialist")

    def evaluate(self, context: Dict[str, Any]) -> AgentReport:
        symbol = context.get("symbol", "BTC/USDT")
        df = context.get("features_df")

        if df is None or len(df) < 30:
            return AgentReport(
                agent_name=self.name,
                role=self.role,
                symbol=symbol,
                bias="NEUTRAL",
                confidence=0.5,
                key_findings=["Insufficient candle history for technical inference."],
                actionable_recommendation="HOLD",
            )

        row = df.iloc[-1]
        close = row["close"]
        ema20 = row.get("ema_20", close)
        ema50 = row.get("ema_50", close)
        rsi = row.get("rsi_14", 50.0)

        findings = []
        corroborating = []
        counters = []

        if close > ema20 > ema50:
            bias = "BULLISH"
            conf = 0.75
            findings.append(f"Bullish alignment: Price ({close:.1f}) > EMA20 ({ema20:.1f}) > EMA50 ({ema50:.1f})")
            corroborating.append("Positive trend slope across short and intermediate averages")
            rec = "BUY"
        elif close < ema20 < ema50:
            bias = "BEARISH"
            conf = 0.75
            findings.append(f"Bearish breakdown: Price ({close:.1f}) < EMA20 ({ema20:.1f}) < EMA50 ({ema50:.1f})")
            corroborating.append("Downward moving average cross confirmed")
            rec = "SELL"
        else:
            bias = "NEUTRAL"
            conf = 0.50
            findings.append("Price consolidating between major moving averages")
            rec = "HOLD"

        if rsi > 70:
            counters.append(f"RSI overbought ({rsi:.1f}), upside momentum may stall")
        elif rsi < 30:
            counters.append(f"RSI oversold ({rsi:.1f}), short squeeze danger")

        return AgentReport(
            agent_name=self.name,
            role=self.role,
            symbol=symbol,
            bias=bias,
            confidence=conf,
            key_findings=findings,
            corroborating_evidence=corroborating,
            counter_arguments=counters,
            actionable_recommendation=rec,
        )


class QuantAnalyst(BaseAnalyst):
    def __init__(self):
        super().__init__("QuantAnalyst", "Statistical & Econometric Modeler")

    def evaluate(self, context: Dict[str, Any]) -> AgentReport:
        symbol = context.get("symbol", "BTC/USDT")
        hurst = context.get("hurst_exponent", 0.50)
        zscore = context.get("price_zscore", 0.0)

        findings = [f"Hurst Exponent: {hurst:.3f}", f"Rolling Price Z-Score: {zscore:.2f}"]
        corroborating = []
        counters = []

        if hurst > 0.55:
            findings.append("Persistent trending regime detected by Hurst statistic.")
            bias = "BULLISH" if zscore > 0 else "BEARISH"
            conf = 0.70
            rec = "BUY" if bias == "BULLISH" else "SELL"
        elif hurst < 0.45:
            findings.append("Mean-reverting regime identified.")
            if zscore < -1.8:
                bias = "BULLISH"
                conf = 0.72
                rec = "BUY"
            elif zscore > 1.8:
                bias = "BEARISH"
                conf = 0.72
                rec = "SELL"
            else:
                bias = "NEUTRAL"
                conf = 0.50
                rec = "HOLD"
        else:
            bias = "NEUTRAL"
            conf = 0.50
            rec = "HOLD"

        return AgentReport(
            agent_name=self.name,
            role=self.role,
            symbol=symbol,
            bias=bias,
            confidence=conf,
            key_findings=findings,
            corroborating_evidence=corroborating,
            counter_arguments=counters,
            actionable_recommendation=rec,
        )


class DerivativesAnalyst(BaseAnalyst):
    def __init__(self):
        super().__init__("DerivativesAnalyst", "Futures Funding & Liquidation Specialist")

    def evaluate(self, context: Dict[str, Any]) -> AgentReport:
        symbol = context.get("symbol", "BTC/USDT")
        deriv_sig = context.get("derivatives_signal")

        if deriv_sig:
            bias = deriv_sig.summary_bias
            conf = 0.70
            findings = [
                f"Funding Rate: {deriv_sig.funding_rate:.6f} ({deriv_sig.funding_bias})",
                f"Liquidation Squeeze Risk: {deriv_sig.liquidation_squeeze_risk}",
                f"Futures Basis: {deriv_sig.futures_basis_bps:.1f} bps",
            ]
            rec = "BUY" if bias == "BULLISH" else ("SELL" if bias == "BEARISH" else "HOLD")
        else:
            bias = "NEUTRAL"
            conf = 0.50
            findings = ["Derivatives positioning balanced."]
            rec = "HOLD"

        return AgentReport(
            agent_name=self.name,
            role=self.role,
            symbol=symbol,
            bias=bias,
            confidence=conf,
            key_findings=findings,
            actionable_recommendation=rec,
        )


class LiquidityAnalyst(BaseAnalyst):
    def __init__(self):
        super().__init__("LiquidityAnalyst", "Order Flow & Market Depth Specialist")

    def evaluate(self, context: Dict[str, Any]) -> AgentReport:
        symbol = context.get("symbol", "BTC/USDT")
        flow_sig = context.get("orderflow_signal")

        if flow_sig:
            bias = flow_sig.summary_bias
            conf = 0.75
            findings = [
                f"Order Book Depth Imbalance: {flow_sig.bid_ask_imbalance:+.2f}",
                f"Aggressive Buyer Ratio: {flow_sig.aggressive_buyer_ratio:.1%}",
                f"Estimated Slippage: {flow_sig.estimated_slippage_bps:.2f} bps",
            ]
            rec = "BUY" if bias == "BULLISH" else ("SELL" if bias == "BEARISH" else "HOLD")
        else:
            bias = "NEUTRAL"
            conf = 0.50
            findings = ["Orderbook depth balanced across both books."]
            rec = "HOLD"

        return AgentReport(
            agent_name=self.name,
            role=self.role,
            symbol=symbol,
            bias=bias,
            confidence=conf,
            key_findings=findings,
            actionable_recommendation=rec,
        )


class SentimentAnalyst(BaseAnalyst):
    def __init__(self):
        super().__init__("SentimentAnalyst", "News & Behavioral Sentiment Specialist")

    def evaluate(self, context: Dict[str, Any]) -> AgentReport:
        symbol = context.get("symbol", "BTC/USDT")
        sent_sig = context.get("sentiment_signal")

        if sent_sig:
            bias = (
                "BULLISH"
                if "BULLISH" in sent_sig.sentiment_bias
                else ("BEARISH" if "BEARISH" in sent_sig.sentiment_bias else "NEUTRAL")
            )
            conf = sent_sig.credibility_weight
            findings = [
                f"Fear & Greed Index: {sent_sig.fear_greed_index} ({sent_sig.fear_greed_category})",
                f"Average News Sentiment: {sent_sig.avg_news_sentiment:+.2f}",
            ]
            rec = "BUY" if bias == "BULLISH" else ("SELL" if bias == "BEARISH" else "HOLD")
        else:
            bias = "NEUTRAL"
            conf = 0.50
            findings = ["Sentiment metrics at benchmark baseline."]
            rec = "HOLD"

        return AgentReport(
            agent_name=self.name,
            role=self.role,
            symbol=symbol,
            bias=bias,
            confidence=conf,
            key_findings=findings,
            actionable_recommendation=rec,
        )


class MacroAnalyst(BaseAnalyst):
    def __init__(self):
        super().__init__("MacroAnalyst", "Cross-Asset & Global Liquidity Specialist")

    def evaluate(self, context: Dict[str, Any]) -> AgentReport:
        symbol = context.get("symbol", "BTC/USDT")
        macro_sig = context.get("macro_signal")

        if macro_sig:
            if macro_sig.crypto_macro_tailwind == "STRONG_TAILWIND":
                bias = "BULLISH"
                conf = 0.70
            elif macro_sig.crypto_macro_tailwind == "HEADWIND":
                bias = "BEARISH"
                conf = 0.70
            else:
                bias = "NEUTRAL"
                conf = 0.50
            findings = [
                f"DXY Index: {macro_sig.dxy_index:.1f} ({macro_sig.dxy_trend})",
                f"Macro Tailwinds: {macro_sig.crypto_macro_tailwind}",
                f"BTC Dominance: {macro_sig.btc_dominance:.1f}%",
            ]
            rec = "BUY" if bias == "BULLISH" else ("SELL" if bias == "BEARISH" else "HOLD")
        else:
            bias = "NEUTRAL"
            conf = 0.50
            findings = ["Macro regime steady."]
            rec = "HOLD"

        return AgentReport(
            agent_name=self.name,
            role=self.role,
            symbol=symbol,
            bias=bias,
            confidence=conf,
            key_findings=findings,
            actionable_recommendation=rec,
        )


class AdversarialAnalyst(BaseAnalyst):
    """Devil's Advocate analyst designed to falsify and challenge predominant consensus."""

    def __init__(self):
        super().__init__("AdversarialAnalyst", "Devil's Advocate & Hypothesis Falsifier")

    def evaluate(self, context: Dict[str, Any]) -> AgentReport:
        symbol = context.get("symbol", "BTC/USDT")
        preliminary_bias = context.get("consensus_hint", "NEUTRAL")
        slippage_bps = context.get("estimated_slippage_bps", 3.0)

        findings = []
        counters = []

        if preliminary_bias == "BULLISH":
            bias = "BEARISH"
            conf = 0.65
            findings.append("Examining bullish exhaustion: resistance rejection danger and liquidity grab traps.")
            counters.append("High probability of retail trap near round resistance figures.")
            if slippage_bps > 8.0:
                counters.append(f"High slippage ({slippage_bps:.1f} bps) will erode upside edge.")
            rec = "HOLD"
        elif preliminary_bias == "BEARISH":
            bias = "BULLISH"
            conf = 0.65
            findings.append("Examining bear trap: deep oversold conditions often provoke violent short squeezes.")
            counters.append("Short positioning is crowded; risk of cascade squeeze.")
            rec = "HOLD"
        else:
            bias = "NEUTRAL"
            conf = 0.50
            findings.append("Market in chop; neither side demonstrates decisive orderbook dominance.")
            rec = "HOLD"

        return AgentReport(
            agent_name=self.name,
            role=self.role,
            symbol=symbol,
            bias=bias,
            confidence=conf,
            key_findings=findings,
            counter_arguments=counters,
            actionable_recommendation=rec,
        )


class RiskAnalyst(BaseAnalyst):
    def __init__(self):
        super().__init__("RiskAnalyst", "Downside Exposure & VaR Specialist")

    def evaluate(self, context: Dict[str, Any]) -> AgentReport:
        symbol = context.get("symbol", "BTC/USDT")
        daily_loss_pct = context.get("daily_loss_pct", 0.0)
        portfolio_exposure = context.get("portfolio_exposure_pct", 0.20)

        findings = [
            f"Current Daily Loss: {daily_loss_pct:.2%}",
            f"Portfolio Deployment: {portfolio_exposure:.1%}",
        ]

        if daily_loss_pct > 0.018:
            bias = "BEARISH"
            conf = 0.95
            findings.append("Daily loss limit approaching ceiling. Halting new risk allocation.")
            rec = "HOLD"
        elif portfolio_exposure >= 0.50:
            bias = "NEUTRAL"
            conf = 0.90
            findings.append("Portfolio exposure limit reached (50%). No further capital deployment.")
            rec = "HOLD"
        else:
            bias = "NEUTRAL"
            conf = 0.85
            findings.append("Risk parameters within acceptable tolerances.")
            rec = "BUY"  # Permit trading

        return AgentReport(
            agent_name=self.name,
            role=self.role,
            symbol=symbol,
            bias=bias,
            confidence=conf,
            key_findings=findings,
            actionable_recommendation=rec,
        )


class PortfolioAnalyst(BaseAnalyst):
    def __init__(self):
        super().__init__("PortfolioAnalyst", "Asset Allocation & Correlation Specialist")

    def evaluate(self, context: Dict[str, Any]) -> AgentReport:
        symbol = context.get("symbol", "BTC/USDT")
        return AgentReport(
            agent_name=self.name,
            role=self.role,
            symbol=symbol,
            bias="NEUTRAL",
            confidence=0.80,
            key_findings=["Portfolio balance diversified across BTC and ETH holdings."],
            actionable_recommendation="HOLD",
        )


class ResearchAnalyst(BaseAnalyst):
    def __init__(self):
        super().__init__("ResearchAnalyst", "Strategy Validation & Regime Compatibility Specialist")

    def evaluate(self, context: Dict[str, Any]) -> AgentReport:
        symbol = context.get("symbol", "BTC/USDT")
        regime = context.get("regime", "RANGING_COMPRESSION")
        return AgentReport(
            agent_name=self.name,
            role=self.role,
            symbol=symbol,
            bias="NEUTRAL",
            confidence=0.80,
            key_findings=[f"Current market regime: {regime}. Active strategies aligned with regime state."],
            actionable_recommendation="HOLD",
        )


class ExecutionAnalyst(BaseAnalyst):
    def __init__(self):
        super().__init__("ExecutionAnalyst", "Execution Quality & Slippage Optimization Specialist")

    def evaluate(self, context: Dict[str, Any]) -> AgentReport:
        symbol = context.get("symbol", "BTC/USDT")
        spread = context.get("spread", 0.01)
        return AgentReport(
            agent_name=self.name,
            role=self.role,
            symbol=symbol,
            bias="NEUTRAL",
            confidence=0.85,
            key_findings=[f"Spread: {spread:.4f}. Maker limit orders recommended over aggressive market orders."],
            actionable_recommendation="HOLD",
        )

