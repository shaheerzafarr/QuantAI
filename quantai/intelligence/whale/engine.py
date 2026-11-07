"""Cryptocurrency Whale & Institutional Wallet Intelligence Engine."""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple
from quantai.config.settings import get_config
from quantai.ingestion.schema import BlockchainTxData
from quantai.storage.db import get_db_manager
from quantai.storage.models import WalletAddress, WalletPerformance, WhaleEvent


class WalletCategory(str, Enum):
    EXCHANGE = "EXCHANGE"
    INSTITUTIONAL = "INSTITUTIONAL"
    MARKET_MAKER = "MARKET_MAKER"
    SMART_MONEY = "SMART_MONEY"
    WHALE = "WHALE"
    UNKNOWN = "UNKNOWN"


@dataclass
class WhaleSignal:
    event_id: str
    timestamp: str
    asset: str
    event_type: str  # ACCUMULATION, DISTRIBUTION, EXCHANGE_INFLOW, EXCHANGE_OUTFLOW
    usd_value: float
    source_category: str
    dest_category: str
    signal_bias: str  # BULLISH, BEARISH, NEUTRAL
    attribution_confidence: float
    smart_money_score: float
    actionable_signal: bool


class WhaleIntelligenceEngine:
    """Tracks, classifies, and evaluates large blockchain transactions and smart-money wallets."""

    def __init__(self):
        self.config = get_config()
        self.db_manager = get_db_manager()

    def get_wallet_category(self, address: str) -> Tuple[str, float]:
        """Query wallet address classification and confidence from database or known registry."""
        with self.db_manager.get_session() as session:
            record = session.query(WalletAddress).filter(WalletAddress.address == address).first()
            if record:
                return record.category, record.attribution_confidence
            # Known heuristics
            if address.lower().startswith("0x_binance") or "binance" in address.lower():
                return WalletCategory.EXCHANGE.value, 0.95
            if address.lower().startswith("0x_coinbase") or "coinbase" in address.lower():
                return WalletCategory.EXCHANGE.value, 0.95
            return WalletCategory.UNKNOWN.value, 0.50

    def compute_smart_money_score(
        self,
        win_rate: float,
        profit_factor: float,
        total_trades: int,
        max_drawdown: float,
        confidence: float,
    ) -> float:
        """
        Calculates a Bayesian-adjusted Smart-Money Intelligence Score (0 to 100).
        Penalizes low sample size and extreme drawdowns.
        """
        if total_trades < 5:
            return 30.0 * confidence  # Insufficient data

        # Sample size shrinkage factor (approaches 1.0 around 50 trades)
        sample_weight = min(1.0, max(0.2, total_trades / 50.0))

        # Baseline score components
        # Win rate component: 50% = 62.5 pts, 70% = 87.5 pts
        win_rate_comp = max(0.0, min(100.0, win_rate * 125.0))
        # Profit factor: 1.0 = 40 pts, 2.0 = 80 pts, 2.5 = 100 pts
        pf_comp = max(0.0, min(100.0, profit_factor * 40.0))
        # Drawdown penalty
        dd_penalty = min(40.0, max_drawdown * 100.0)

        raw_score = (win_rate_comp * 0.50 + pf_comp * 0.50) - (dd_penalty * 0.25)
        # Apply shrinkage and attribution confidence
        shrunk_score = 50.0 + (raw_score - 50.0) * sample_weight
        final_score = max(0.0, min(100.0, shrunk_score * (0.50 + 0.50 * confidence)))
        return round(final_score, 2)

    def process_transaction(self, tx: BlockchainTxData) -> Optional[WhaleSignal]:
        """Analyzes a blockchain transfer for institutional flow and whale accumulation/distribution."""
        threshold = (
            self.config.intelligence.whale.btc_whale_usd_threshold
            if "BTC" in tx.symbol
            else self.config.intelligence.whale.eth_whale_usd_threshold
        )

        if tx.usd_value < threshold:
            return None  # Below whale threshold

        from_cat, from_conf = self.get_wallet_category(tx.from_address)
        to_cat, to_conf = self.get_wallet_category(tx.to_address)
        combined_conf = (from_conf + to_conf) / 2.0

        # Flow direction rules
        # 1. Transfer to exchange => Inflow (Potential selling pressure)
        if to_cat == WalletCategory.EXCHANGE.value and from_cat != WalletCategory.EXCHANGE.value:
            event_type = "EXCHANGE_INFLOW"
            signal_bias = "BEARISH"
        # 2. Transfer from exchange to private wallet => Outflow (Accumulation/cold storage)
        elif from_cat == WalletCategory.EXCHANGE.value and to_cat != WalletCategory.EXCHANGE.value:
            event_type = "EXCHANGE_OUTFLOW"
            signal_bias = "BULLISH"
        # 3. Large transfer between unknown/smart money wallets
        elif to_cat == WalletCategory.SMART_MONEY.value:
            event_type = "SMART_MONEY_ACCUMULATION"
            signal_bias = "BULLISH"
        else:
            event_type = "LARGE_WALLET_TRANSFER"
            signal_bias = "NEUTRAL"

        # Check if actionable: requires high attribution confidence and non-neutral bias
        actionable = (combined_conf >= 0.70) and (signal_bias != "NEUTRAL") and (tx.usd_value >= threshold * 1.5)

        # Record WhaleEvent in DB
        try:
            with self.db_manager.get_session() as session:
                we = WhaleEvent(
                    event_type=event_type,
                    asset=tx.symbol,
                    amount=tx.amount,
                    usd_value=tx.usd_value,
                    source_wallet=tx.from_address,
                    dest_wallet=tx.to_address,
                    signal_bias=signal_bias,
                    confidence=combined_conf,
                    timestamp=tx.event_time,
                )
                session.add(we)
        except Exception:
            pass

        return WhaleSignal(
            event_id=tx.tx_hash,
            timestamp=tx.event_time.isoformat(),
            asset=tx.symbol,
            event_type=event_type,
            usd_value=tx.usd_value,
            source_category=from_cat,
            dest_category=to_cat,
            signal_bias=signal_bias,
            attribution_confidence=combined_conf,
            smart_money_score=78.5,  # Baseline score for verified institutional flows
            actionable_signal=actionable,
        )

    def evaluate_live_whale_tape(self, symbol: str, whale_data: Dict[str, Any]) -> Optional[WhaleSignal]:
        """Converts live Binance Futures aggregated whale orderflow into a structured WhaleSignal."""
        count = whale_data.get("whale_trade_count", 0)
        net_delta = whale_data.get("whale_net_delta_usd", 0.0)
        bias = whale_data.get("whale_bias", "NEUTRAL")
        total_vol = whale_data.get("whale_buy_vol_usd", 0.0) + whale_data.get("whale_sell_vol_usd", 0.0)

        if count == 0 or total_vol == 0:
            return None

        actionable = bias in ["BULLISH", "BEARISH"] and abs(net_delta) >= 50_000.0
        conf = 0.85 if abs(net_delta) >= 150_000.0 else (0.75 if actionable else 0.50)
        smart_money = round(min(95.0, 50.0 + (abs(net_delta) / total_vol) * 45.0), 1)

        return WhaleSignal(
            event_id=f"WHALE_TAPE_{int(datetime.now(timezone.utc).timestamp())}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            asset=symbol,
            event_type="INSTITUTIONAL_SWEEP" if abs(net_delta) >= 100_000 else "ORDERFLOW_ACCUMULATION",
            usd_value=total_vol,
            source_category="BINANCE_FUTURES_TAPE",
            dest_category="AGGRESSIVE_TAKERS",
            signal_bias=bias,
            attribution_confidence=conf,
            smart_money_score=smart_money,
            actionable_signal=actionable,
        )
