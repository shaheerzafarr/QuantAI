"""Live Financial & Crypto News Intelligence Feed.

Continuously pulls breaking news headlines from CoinDesk, CoinTelegraph,
and financial RSS streams, scores sentiment, and detects token-specific regulatory
or exploit shock events to prevent blind trades.
"""

import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import requests

from quantai.intelligence.sentiment.analyzer import SentimentSignal

logger = logging.getLogger("quantai.news_feed")

NEGATIVE_SHOCK_KEYWORDS = [
    "hack", "hacked", "exploit", "breach", "stolen", "sec", "lawsuit", "investigation",
    "illicit", "sanctions", "fraud", "subpoena", "halt", "delist", "scam", "freeze",
    "indictment", "insolvent", "bankruptcy", "liquidation",
]

POSITIVE_CATALYST_KEYWORDS = [
    "approval", "approved", "etf", "partnership", "mainnet", "record high", "surge",
    "breakout", "rally", "adoption", "upgrade", "launch", "cleared", "dismissed",
]

TOKEN_SYNONYMS = {
    "BTC": ["btc", "bitcoin"],
    "ETH": ["eth", "ethereum", "ether"],
    "SOL": ["sol", "solana"],
    "XRP": ["xrp", "ripple"],
    "DOGE": ["doge", "dogecoin"],
    "ZEC": ["zec", "zcash"],
    "ADA": ["ada", "cardano"],
    "AVAX": ["avax", "avalanche"],
    "SUI": ["sui"],
    "NEAR": ["near"],
}


class LiveNewsFeedAnalyzer:
    """Continuously monitors live crypto headlines and calculates real-time sentiment."""

    def __init__(self, cache_ttl_seconds: float = 180.0):
        self.cache_ttl = cache_ttl_seconds
        self.last_fetch_time = 0.0
        self.cached_articles: List[Dict[str, Any]] = []
        self.feed_urls = [
            "https://www.coindesk.com/arc/outboundfeeds/rss/",
            "https://cointelegraph.com/rss",
        ]

    def refresh_feeds_if_needed(self):
        """Fetches latest RSS items if cache has expired."""
        now = time.time()
        if now - self.last_fetch_time < self.cache_ttl and self.cached_articles:
            return

        articles = []
        for url in self.feed_urls:
            try:
                resp = requests.get(
                    url,
                    timeout=5,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) QuantAI/2.0"},
                )
                if resp.status_code == 200:
                    root = ET.fromstring(resp.content)
                    items = root.findall(".//item")
                    for item in items[:25]:
                        title = item.find("title").text if item.find("title") is not None else ""
                        pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
                        if title:
                            articles.append({
                                "title": title.strip(),
                                "pub_date": pub_date.strip(),
                                "source": "CoinDesk" if "coindesk" in url else "CoinTelegraph",
                            })
            except Exception as e:
                logger.debug(f"RSS feed fetch notice for {url}: {e}")

        if articles:
            self.cached_articles = articles
            self.last_fetch_time = now
            logger.info(f"Refreshed live news feed: {len(articles)} headlines cached.")

    def evaluate_token_sentiment(self, symbol: str) -> Dict[str, Any]:
        """Analyzes breaking news specifically relevant to the token symbol."""
        self.refresh_feeds_if_needed()

        base_asset = symbol.split("/")[0].upper()
        synonyms = TOKEN_SYNONYMS.get(base_asset, [base_asset.lower()])

        relevant_headlines = []
        negative_shocks = []
        positive_catalysts = []

        for art in self.cached_articles:
            title_lower = art["title"].lower()
            # Check if headline is relevant to this token or market-wide
            is_relevant = any(syn in title_lower.split() or f"${syn}" in title_lower for syn in synonyms)
            is_macro = any(m in title_lower for m in ["crypto", "bitcoin", "fed", "treasury", "sec"])

            if is_relevant or (base_asset in ["BTC", "ETH"] and is_macro):
                relevant_headlines.append(art["title"])
                for neg in NEGATIVE_SHOCK_KEYWORDS:
                    if neg in title_lower:
                        negative_shocks.append(f"{neg.upper()}: {art['title']}")
                        break
                for pos in POSITIVE_CATALYST_KEYWORDS:
                    if pos in title_lower:
                        positive_catalysts.append(f"{pos.upper()}: {art['title']}")
                        break

        # Compute sentiment score (-1.0 to +1.0)
        neg_count = len(negative_shocks)
        pos_count = len(positive_catalysts)
        total_signals = neg_count + pos_count

        if total_signals > 0:
            score = (pos_count - neg_count) / float(total_signals)
        else:
            score = 0.0

        if score > 0.25:
            bias = "BULLISH"
        elif score < -0.25:
            bias = "BEARISH"
        else:
            bias = "NEUTRAL"

        return {
            "symbol": symbol,
            "sentiment_score": round(score, 2),
            "bias": bias,
            "has_negative_shock": len(negative_shocks) > 0,
            "negative_shocks": negative_shocks[:3],
            "positive_catalysts": positive_catalysts[:3],
            "total_relevant_headlines": len(relevant_headlines),
            "sample_headlines": relevant_headlines[:3],
        }

    def build_sentiment_signal(self, symbol: str) -> SentimentSignal:
        """Constructs a structured SentimentSignal for MultiAgentSwarm consumption."""
        res = self.evaluate_token_sentiment(symbol)
        score = res["sentiment_score"]
        bias = res["bias"]
        count = res["total_relevant_headlines"]

        # Approximate Fear and Greed based on news balance
        fng_val = int(50 + (score * 30))
        fng_val = max(10, min(90, fng_val))
        fng_cat = "Greed" if fng_val > 60 else ("Fear" if fng_val < 40 else "Neutral")

        return SentimentSignal(
            timestamp=datetime.now(timezone.utc).isoformat(),
            fear_greed_index=fng_val,
            fear_greed_category=fng_cat,
            avg_news_sentiment=score,
            sentiment_bias=bias,
            credibility_weight=min(0.95, 0.50 + (count * 0.1)),
            headline_count=count,
        )

