"""Vectorized Technical Indicator Library for QuantAI.

Pure Python / NumPy / Pandas implementation ensuring zero external C-compilation
dependencies, strict mathematical precision, and complete prevention of lookahead bias.
"""

from typing import Dict, Tuple
import numpy as np
from quantai.common import pd


class TechnicalIndicators:
    """Calculates professional-grade technical market features."""

    @staticmethod
    def sma(series: pd.Series, period: int = 20) -> pd.Series:
        return series.rolling(window=period).mean()

    @staticmethod
    def ema(series: pd.Series, period: int = 20) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def macd(
        close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        ema_fast = TechnicalIndicators.ema(close, fast)
        ema_slow = TechnicalIndicators.ema(close, slow)
        macd_line = ema_fast - ema_slow
        signal_line = TechnicalIndicators.ema(macd_line, signal)
        hist = macd_line - signal_line
        return macd_line, signal_line, hist

    @staticmethod
    def rsi(close: pd.Series, period: int = 14) -> pd.Series:
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)

        avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()

        rs = avg_gain / (avg_loss + 1e-10)
        rsi = 100.0 - (100.0 / (1.0 + rs))
        return rsi

    @staticmethod
    def stoch_rsi(
        close: pd.Series,
        rsi_period: int = 14,
        stoch_period: int = 14,
        k_period: int = 3,
        d_period: int = 3,
    ) -> Tuple[pd.Series, pd.Series]:
        """Calculates Stochastic RSI (%K and %D lines) bounded between 0 and 100."""
        rsi_vals = TechnicalIndicators.rsi(close, period=rsi_period)
        min_rsi = rsi_vals.rolling(window=stoch_period).min()
        max_rsi = rsi_vals.rolling(window=stoch_period).max()
        stoch = (rsi_vals - min_rsi) / (max_rsi - min_rsi + 1e-10) * 100.0
        k = stoch.rolling(window=k_period).mean()
        d = k.rolling(window=d_period).mean()
        return k, d

    @staticmethod
    def bollinger_bands(
        close: pd.Series, period: int = 20, num_std: float = 2.0
    ) -> Tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
        mid = close.rolling(window=period).mean()
        std = close.rolling(window=period).std()
        upper = mid + num_std * std
        lower = mid - num_std * std
        width = (upper - lower) / (mid + 1e-10)
        return upper, mid, lower, width

    @staticmethod
    def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        prev_close = close.shift(1)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()

    @staticmethod
    def supertrend(
        high: pd.Series, low: pd.Series, close: pd.Series, period: int = 10, multiplier: float = 3.0
    ) -> Tuple[pd.Series, pd.Series]:
        """Calculates Supertrend line and directional signal (+1 bull, -1 bear)."""
        atr_val = TechnicalIndicators.atr(high, low, close, period)
        hl2 = (high + low) / 2.0
        basic_upper = hl2 + (multiplier * atr_val)
        basic_lower = hl2 - (multiplier * atr_val)

        final_upper = basic_upper.copy()
        final_lower = basic_lower.copy()
        supertrend = pd.Series(index=close.index, dtype=float)
        direction = pd.Series(index=close.index, dtype=int)

        for i in range(1, len(close)):
            # Upper band
            if basic_upper.iloc[i] < final_upper.iloc[i - 1] or close.iloc[i - 1] > final_upper.iloc[i - 1]:
                final_upper.iloc[i] = basic_upper.iloc[i]
            else:
                final_upper.iloc[i] = final_upper.iloc[i - 1]

            # Lower band
            if basic_lower.iloc[i] > final_lower.iloc[i - 1] or close.iloc[i - 1] < final_lower.iloc[i - 1]:
                final_lower.iloc[i] = basic_lower.iloc[i]
            else:
                final_lower.iloc[i] = final_lower.iloc[i - 1]

            # Direction
            if i == 1:
                direction.iloc[i] = 1 if close.iloc[i] > final_upper.iloc[i] else -1
            else:
                if supertrend.iloc[i - 1] == final_upper.iloc[i - 1]:
                    direction.iloc[i] = 1 if close.iloc[i] > final_upper.iloc[i] else -1
                else:
                    direction.iloc[i] = -1 if close.iloc[i] < final_lower.iloc[i] else 1

            supertrend.iloc[i] = final_lower.iloc[i] if direction.iloc[i] == 1 else final_upper.iloc[i]

        return supertrend, direction

    @staticmethod
    def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
        typical_price = (high + low + close) / 3.0
        pv = typical_price * volume
        return pv.cumsum() / (volume.cumsum() + 1e-10)

    @staticmethod
    def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
        diff_vals = close.diff().values if hasattr(close.diff(), "values") else np.asarray(close.diff())
        direction = np.sign(diff_vals)
        if len(direction) > 0:
            direction[0] = 0
        vol_arr = volume.values if hasattr(volume, "values") else np.asarray(volume)
        res = np.cumsum(direction * vol_arr)
        return pd.Series(res)

    @staticmethod
    def volume_profile_poc(close: pd.Series, volume: pd.Series, bins: int = 20) -> Dict[str, float]:
        """Calculates Point of Control (POC), Value Area High (VAH), Value Area Low (VAL)."""
        if len(close) == 0:
            return {"poc": 0.0, "vah": 0.0, "val": 0.0}

        counts, edges = np.histogram(close, bins=bins, weights=volume)
        max_idx = np.argmax(counts)
        poc = (edges[max_idx] + edges[max_idx + 1]) / 2.0

        total_vol = counts.sum()
        value_area_vol = total_vol * 0.70  # Standard 70% value area

        sorted_indices = np.argsort(counts)[::-1]
        accumulated = 0.0
        selected_bins = []
        for idx in sorted_indices:
            accumulated += counts[idx]
            selected_bins.append(idx)
            if accumulated >= value_area_vol:
                break

        vah = max(edges[idx + 1] for idx in selected_bins)
        val = min(edges[idx] for idx in selected_bins)
        return {"poc": float(poc), "vah": float(vah), "val": float(val)}

    @staticmethod
    def pivot_points(high: float, low: float, close: float) -> Dict[str, float]:
        """Calculates classic Floor Pivot Points."""
        pivot = (high + low + close) / 3.0
        r1 = 2 * pivot - low
        s1 = 2 * pivot - high
        r2 = pivot + (high - low)
        s2 = pivot - (high - low)
        r3 = high + 2 * (pivot - low)
        s3 = low - 2 * (high - pivot)
        return {"pivot": pivot, "r1": r1, "s1": s1, "r2": r2, "s2": s2, "r3": r3, "s3": s3}
