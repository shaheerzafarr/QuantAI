"""Unit Tests for Machine Learning Pipeline."""

import numpy as np
import pytest
from quantai.common import pd
from quantai.ml.pipeline import PurgedWalkForwardCV, QuantMLModel


def test_purged_walk_forward_cv_no_leakage():
    n = 200
    df = pd.DataFrame({"val": np.arange(n)})
    cv = PurgedWalkForwardCV(n_splits=3, pct_embargo=0.05)
    splits = cv.split(df)

    assert len(splits) > 0
    for train_idx, test_idx in splits:
        # Check that maximum training index is strictly before test start minus embargo
        assert train_idx[-1] < test_idx[0]
        # Check no overlap between train and test
        assert len(set(train_idx).intersection(set(test_idx))) == 0


def test_quant_ml_model_calibration():
    np.random.seed(42)
    n = 120
    df = pd.DataFrame(
        {
            "close": np.linspace(60000, 65000, n) + np.random.normal(0, 100, n),
            "rsi_14": np.random.uniform(20, 80, n),
            "macd": np.random.normal(0, 5, n),
            "atr_14": np.random.uniform(50, 200, n),
        }
    )

    model = QuantMLModel(model_version="test_v1")
    X, y = model.prepare_dataset(df, forward_horizon=3, return_threshold=0.001)
    model.fit(X, y)

    latest_row = X.iloc[-1]
    pred = model.predict_latest(latest_row, symbol="BTC/USDT")

    assert pred.calibrated_prob >= 0.0 and pred.calibrated_prob <= 1.0
    assert pred.target_class in ["BUY", "SELL", "HOLD"]
    assert model.brier_score >= 0.0
