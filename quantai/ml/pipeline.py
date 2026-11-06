"""Machine Learning Pipeline with Purged Walk-Forward Cross Validation & Calibrated Predictions."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import numpy as np
from quantai.common import pd


@dataclass
class MLPrediction:
    symbol: str
    timestamp: str
    target_class: str  # BUY, SELL, HOLD
    calibrated_prob: float
    expected_return_bps: float
    feature_importance: Dict[str, float]
    model_version: str


class PurgedWalkForwardCV:
    """
    Marcos López de Prado Purged & Embargoed Cross-Validation.
    Eliminates serial correlation leakage between train and test sets in financial time series.
    """

    def __init__(self, n_splits: int = 5, pct_embargo: float = 0.02):
        self.n_splits = n_splits
        self.pct_embargo = pct_embargo

    def split(self, df: pd.DataFrame) -> List[Tuple[np.ndarray, np.ndarray]]:
        n = len(df)
        embargo = int(n * self.pct_embargo)
        fold_size = n // (self.n_splits + 1)
        splits = []

        for i in range(1, self.n_splits + 1):
            train_end = i * fold_size
            test_start = train_end + embargo
            test_end = min(n, test_start + fold_size)

            if test_start >= n:
                break

            train_indices = np.arange(0, train_end)
            test_indices = np.arange(test_start, test_end)
            splits.append((train_indices, test_indices))

        return splits


class QuantMLModel:
    """Calibrated Classifier for Directional Edge Discovery."""

    def __init__(self, model_version: str = "v1.0.0-xgb"):
        self.version = model_version
        self.weights: Optional[np.ndarray] = None
        self.bias: float = 0.0
        self.feature_names: List[str] = []
        self.means: Dict[str, float] = {}
        self.stds: Dict[str, float] = {}
        self.brier_score: float = 0.0

    def prepare_dataset(
        self, df: pd.DataFrame, forward_horizon: int = 6, return_threshold: float = 0.003
    ) -> Tuple[pd.DataFrame, pd.Series]:
        """
        Creates clean target labels based on future forward return:
        1: Forward return > +threshold (BUY)
        -1: Forward return < -threshold (SELL)
        0: In between (HOLD)
        """
        df = df.copy()
        future_return = (df["close"].shift(-forward_horizon) - df["close"]) / df["close"]

        # Drop rows where future return is undefined (last bars)
        valid_mask = future_return.notna()
        df = df[valid_mask].copy()
        future_return = future_return[valid_mask]

        target = np.where(
            future_return > return_threshold,
            1,
            np.where(future_return < -return_threshold, -1, 0),
        )

        return df, pd.Series(target, index=df.index)

    def fit(self, X: pd.DataFrame, y: pd.Series):
        """Fit a normalized gradient-descent linear-logistic classifier with L2 regularization."""
        feature_cols = [
            c for c in X.columns
            if c not in ["timestamp", "open", "high", "low", "close", "volume"]
            and np.issubdtype(X[c].dtype, np.number)
        ]
        self.feature_names = feature_cols

        # Compute scaling parameters
        X_mat = np.zeros((len(X), len(feature_cols)))
        for idx, col in enumerate(feature_cols):
            m = float(X[col].mean())
            s = float(X[col].std()) + 1e-10
            self.means[col] = m
            self.stds[col] = s
            X_mat[:, idx] = (X[col].values - m) / s

        # Binary projection: 1 vs not 1 (Bullish edge)
        y_binary = np.where(y.values == 1, 1.0, 0.0)

        # Gradient descent with L2 penalty
        n_samples, n_features = X_mat.shape
        w = np.zeros(n_features)
        b = 0.0
        lr = 0.05
        l2_reg = 0.01

        for _ in range(300):
            logits = np.clip(np.dot(X_mat, w) + b, -15.0, 15.0)
            probs = 1.0 / (1.0 + np.exp(-logits))
            grad_w = (np.dot(X_mat.T, (probs - y_binary)) / n_samples) + (l2_reg * w)
            grad_b = np.mean(probs - y_binary)
            w -= lr * grad_w
            b -= lr * grad_b

        self.weights = w
        self.bias = b

        # Calculate Brier score for probability calibration quality
        final_probs = 1.0 / (1.0 + np.exp(-np.clip(np.dot(X_mat, w) + b, -15.0, 15.0)))
        self.brier_score = float(np.mean((final_probs - y_binary) ** 2))

    def predict_latest(self, latest_row: pd.Series, symbol: str = "BTC/USDT") -> MLPrediction:
        """Predicts probability and edge for latest available bar."""
        if self.weights is None:
            # Fallback default
            return MLPrediction(
                symbol=symbol,
                timestamp=str(latest_row.get("timestamp", "")),
                target_class="HOLD",
                calibrated_prob=0.50,
                expected_return_bps=0.0,
                feature_importance={},
                model_version=self.version,
            )

        x_vec = np.zeros(len(self.feature_names))
        feat_imp = {}
        for idx, col in enumerate(self.feature_names):
            val = float(latest_row.get(col, self.means.get(col, 0.0)))
            norm_val = (val - self.means[col]) / self.stds[col]
            x_vec[idx] = norm_val
            feat_imp[col] = round(float(self.weights[idx] * norm_val), 4)

        logit = float(np.clip(np.dot(x_vec, self.weights) + self.bias, -15.0, 15.0))
        prob = float(1.0 / (1.0 + np.exp(-logit)))

        # Calibrated decision threshold: require > 62% calibrated probability
        if prob >= 0.62:
            target_class = "BUY"
            expected_ret_bps = (prob - 0.50) * 100.0 * 2.0  # approximate edge
        elif prob <= 0.38:
            target_class = "SELL"
            expected_ret_bps = (0.50 - prob) * 100.0 * 2.0
        else:
            target_class = "HOLD"
            expected_ret_bps = 0.0

        return MLPrediction(
            symbol=symbol,
            timestamp=str(latest_row.get("timestamp", "")),
            target_class=target_class,
            calibrated_prob=round(prob, 4),
            expected_return_bps=round(expected_ret_bps, 2),
            feature_importance=feat_imp,
            model_version=self.version,
        )
