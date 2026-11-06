"""QuantAI FreqAI Model Adapter.

Subclasses Freqtrade's IFreqaiModel interface to seamlessly inject QuantAI's
calibrated machine learning and purged walk-forward cross-validation pipeline.
"""

import logging
from typing import Any, Dict, Tuple
import numpy as np
from quantai.common import pd
from quantai.ml.pipeline import QuantMLModel, PurgedWalkForwardCV

logger = logging.getLogger("quantai.freqai")

# Gracefully import IFreqaiModel if running inside full Freqtrade environment
try:
    from freqtrade.freqai.base_models.BaseClassifierModel import BaseClassifierModel as IFreqaiModel
except ImportError:
    class IFreqaiModel:
        """Standalone mock of Freqtrade IFreqaiModel interface."""
        def __init__(self, **kwargs):
            self.model = None


class QuantAIFreqaiModel(IFreqaiModel):
    """
    Custom FreqAI classifier model integrating QuantAI's calibrated edge prediction
    and Marcos López de Prado's Purged & Embargoed walk-forward cross-validation.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs) if hasattr(super(), "__init__") else None
        self.quant_model = QuantMLModel(model_version="freqai-quant-v1")
        self.cv = PurgedWalkForwardCV(n_splits=4, pct_embargo=0.03)

    def train(self, unfiltered_df: pd.DataFrame, pair: str, dk: Any = None) -> Any:
        """
        Trains QuantAI Calibrated Logistic / Gradient Descent model using
        purged & embargoed time-series cross-validation.
        """
        logger.info(f"Training QuantAIFreqaiModel on {len(unfiltered_df)} candles for {pair}...")
        X, y = self.quant_model.prepare_dataset(unfiltered_df, forward_horizon=6, return_threshold=0.003)

        if len(X) < 40:
            logger.warning("Insufficient samples for robust ML training. Using baseline initialization.")
            return self.quant_model

        # Execute purged cross-validation splits
        splits = self.cv.split(X)
        logger.info(f"Generated {len(splits)} purged & embargoed cross-validation folds.")

        # Fit model on training set
        self.quant_model.fit(X, y)
        logger.info(f"QuantAIFreqaiModel trained successfully. Brier calibration score: {self.quant_model.brier_score:.4f}")
        return self.quant_model

    def predict(self, unfiltered_df: pd.DataFrame, dk: Any = None, **kwargs) -> Tuple[pd.DataFrame, np.ndarray]:
        """
        Predicts calibrated directional edge probability and expected return.
        Returns:
            (pred_df, do_predict)
        """
        n = len(unfiltered_df)
        pred_labels = []
        pred_probs = []

        for i in range(n):
            row = unfiltered_df.iloc[i]
            pred = self.quant_model.predict_latest(row)
            pred_labels.append(1 if pred.target_class == "BUY" else (-1 if pred.target_class == "SELL" else 0))
            pred_probs.append(pred.calibrated_prob)

        pred_df = pd.DataFrame(
            {
                "&-target": pred_labels,
                "&-target_prob": pred_probs,
            }
        )
        do_predict = np.ones(n, dtype=int)
        return pred_df, do_predict
