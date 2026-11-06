"""Multi-Timeframe Technical Feature Engineering Engine."""

from datetime import datetime
from typing import Dict, List, Optional
from quantai.common import pd
from quantai.intelligence.technical.indicators import TechnicalIndicators
from quantai.storage.models import MarketCandle


class TechnicalFeatureEngine:
    """Extracts synchronized multi-timeframe technical indicator matrices."""

    def __init__(self, primary_timeframe: str = "5m"):
        self.primary_tf = primary_timeframe
        self.ti = TechnicalIndicators()

    def dataframe_from_candles(self, candles: List[MarketCandle]) -> pd.DataFrame:
        """Converts database or ingested candle records into a clean indexed DataFrame."""
        if not candles:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        data = [
            {
                "timestamp": c.timestamp,
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": float(c.volume),
            }
            for c in candles
        ]
        df = pd.DataFrame(data)
        df.sort_values("timestamp", inplace=True)
        df.reset_index(drop=True, inplace=True)
        return df

    def compute_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute full suite of technical features on a single timeframe dataframe."""
        if len(df) < 30:
            return df

        df = df.copy()

        # Trend features
        df["ema_9"] = self.ti.ema(df["close"], 9)
        df["ema_20"] = self.ti.ema(df["close"], 20)
        df["ema_50"] = self.ti.ema(df["close"], 50)
        df["ema_200"] = self.ti.ema(df["close"], 200)

        # MACD
        df["macd"], df["macd_signal"], df["macd_hist"] = self.ti.macd(df["close"])

        # RSI
        df["rsi_14"] = self.ti.rsi(df["close"], 14)

        # Bollinger Bands
        bb_upper, bb_mid, bb_lower, bb_width = self.ti.bollinger_bands(df["close"])
        df["bb_upper"] = bb_upper
        df["bb_mid"] = bb_mid
        df["bb_lower"] = bb_lower
        df["bb_width"] = bb_width

        # ATR
        df["atr_14"] = self.ti.atr(df["high"], df["low"], df["close"], 14)

        # VWAP & OBV
        df["vwap"] = self.ti.vwap(df["high"], df["low"], df["close"], df["volume"])
        df["obv"] = self.ti.obv(df["close"], df["volume"])

        # Price position relative to EMA
        df["dist_to_ema20_pct"] = (df["close"] - df["ema_20"]) / df["ema_20"]
        df["dist_to_ema200_pct"] = (df["close"] - df["ema_200"]) / (df["ema_200"] + 1e-10)

        # Volatility ratio
        df["volatility_ratio"] = df["atr_14"] / (df["close"] + 1e-10)

        # Fill NaNs from early rolling windows
        df.bfill(inplace=True)
        return df

    def build_multi_timeframe_matrix(
        self,
        base_df: pd.DataFrame,
        higher_tf_dfs: Dict[str, pd.DataFrame],
    ) -> pd.DataFrame:
        """
        Merge higher timeframe features into base timeframe without lookahead bias.
        Uses backward merge_asof so a 5m bar only sees the most recently *closed* 1h/4h bar.
        """
        result_df = self.compute_features(base_df)

        for tf_name, htf_raw in higher_tf_dfs.items():
            if len(htf_raw) == 0:
                continue

            htf_feat = self.compute_features(htf_raw)
            # Prefix columns to avoid collisions
            prefix = f"{tf_name}_"
            rename_dict = {
                col: f"{prefix}{col}"
                for col in htf_feat.columns
                if col not in ["timestamp"]
            }
            htf_feat = htf_feat.rename(columns=rename_dict)

            # Prevent lookahead bias: higher timeframe bar timestamp represents bar open time.
            # In order to ensure only completed candles are visible, we use merge_asof with direction='backward'
            result_df = pd.merge_asof(
                result_df.sort_values("timestamp"),
                htf_feat.sort_values("timestamp"),
                on="timestamp",
                direction="backward",
            )

        return result_df
