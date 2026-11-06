"""QuantAI Common Utilities & Data Compatibility Layer."""

try:
    import pandas as pd
    # Test if pandas C-extensions are functional
    _test = pd.Series([1.0, 2.0]).mean()
except Exception:
    import quantai.common.series as pd

__all__ = ["pd"]
