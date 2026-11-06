"""Sentiment & News Intelligence Analyzer."""

from dataclasses import dataclass
from typing import Dict, List, Optional
from quantai.ingestion.schema import NewsSentimentData


@dataclass
class SentimentSignal:
    timestamp: str
    fear_greed_index: int  # 0 to 100
    fear_greed_category: str  # Extreme Fear, Fear, Neutral, Greed, Extreme Greed
    avg_news_sentiment: float  # -1.0 to +1.0
    sentiment_bias: str  # BULLISH, BEARISH, NEUTRAL
    credibility_weight: float
    headline_count: int


class SentimentAnalyzer:
    """Analyzes market news sentiment and Fear & Greed signals."""

    def __init__(self):
        self._current_fng = 48  # Neutral base

    def set_fear_and_greed(self, value: int):
        self._current_fng = max(0, min(100, value))

    def evaluate(self, articles: List[NewsSentimentData]) -> SentimentSignal:
        if not articles:
            fng_cat = self._get_fng_category(self._current_fng)
            return SentimentSignal(
                timestamp=articles[0].event_time.isoformat() if articles else "",
                fear_greed_index=self._current_fng,
                fear_greed_category=fng_cat,
                avg_news_sentiment=0.0,
                sentiment_bias="NEUTRAL",
                credibility_weight=0.5,
                headline_count=0,
            )

        # Weighted sentiment score
        total_weight = sum(a.impact_weight for a in articles)
        if total_weight > 0:
            weighted_sentiment = sum(a.sentiment_score * a.impact_weight for a in articles) / total_weight
        else:
            weighted_sentiment = 0.0

        fng_cat = self._get_fng_category(self._current_fng)

        # Contrarian or momentum bias
        # Extreme fear (< 25) often marks local bottoms; Extreme greed (> 75) marks overheated tops.
        if self._current_fng < 25 and weighted_sentiment > -0.2:
            sentiment_bias = "BULLISH_CONTRARIAN"
        elif self._current_fng > 80 and weighted_sentiment < 0.2:
            sentiment_bias = "BEARISH_CONTRARIAN"
        elif weighted_sentiment > 0.35:
            sentiment_bias = "BULLISH"
        elif weighted_sentiment < -0.35:
            sentiment_bias = "BEARISH"
        else:
            sentiment_bias = "NEUTRAL"

        return SentimentSignal(
            timestamp=articles[0].event_time.isoformat(),
            fear_greed_index=self._current_fng,
            fear_greed_category=fng_cat,
            avg_news_sentiment=round(weighted_sentiment, 3),
            sentiment_bias=sentiment_bias,
            credibility_weight=min(1.0, len(articles) / 10.0),
            headline_count=len(articles),
        )

    def _get_fng_category(self, val: int) -> str:
        if val <= 25:
            return "Extreme Fear"
        elif val <= 45:
            return "Fear"
        elif val <= 55:
            return "Neutral"
        elif val <= 75:
            return "Greed"
        return "Extreme Greed"

