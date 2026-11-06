"""Research & Strategy Package."""

from quantai.research.strategies import (
    BaseStrategy,
    TrendFollowingStrategy,
    MeanReversionStrategy,
    WhaleFollowingStrategy,
    StrategySignal,
)
from quantai.research.engine import ResearchEngine, BacktestEvaluation

__all__ = [
    "BaseStrategy",
    "TrendFollowingStrategy",
    "MeanReversionStrategy",
    "WhaleFollowingStrategy",
    "StrategySignal",
    "ResearchEngine",
    "BacktestEvaluation",
]
