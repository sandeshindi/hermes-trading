"""
India Financial News Adapter

Primary:  NewsAPI → /v2/everything?q={symbol}+NSE&language=en&sources=the-times-of-india,the-economic-times
          Requires NEWS_API_KEY in .env
Fallback: Economic Times RSS → https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms

Exposes:
  async def fetch(symbol: str) -> dict
    schema_version: "india-news-v1"
    fields: headlines (list[str], max 5), sentiment_score (-1 to +1),
            fetched_at_ist
"""

import os
import httpx
import feedparser
from datetime import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")

def calculate_sentiment(headlines: list[str]) -> float:
    """Lightweight keyword-based sentiment analysis scoring from -1.0 to 1.0."""
    pos_keywords = {"rise", "gains", "jump", "profit", "surges", "up", "buy", "upgrade", "exceed", "bull", "rally", "growth", "high"}
    neg_keywords = {"fall", "losses", "drop", "deficit", "plunge", "down", "sell", "downgrade", "miss", "bear", "slump", "decline", "low"}
    
    score = 0.0
    hits = 0
    for hl in headlines:
        words = hl.lower().split()
        for w in words:
            clean_word = "".join(c for c in w if c.isalnum())
            if clean_word in pos_keywords:
                score += 1.0
                hits += 1
            elif clean_word in neg_keywords:
                score -= 1.0
                hits += 1
                
    if hits == 0:
        return 0.0
    return max(-1.0, min(1.0, score / hits))

async def fetch(symbol: str) -> dict:
    news_api_key = os.getenv("NEWS_API_KEY")
    headlines = []
    
    # 1. Try Primary: NewsAPI
    if news_api_key:
        try:
            url = f"https://newsapi.org/v2/everything?q={symbol}+NSE&language=en&sources=the-times-of-india,the-economic-times&apiKey={news_api_key}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    data = r.json()
                    articles = data.get("articles", [])
                    for art in articles[:5]:
                        title = art.get("title")
                        if title:
                            headlines.append(title)
        except Exception as e:
            # Silence and let it fall back
            pass

    # 2. Fallback: Economic Times RSS
    if not headlines:
        try:
            rss_url = "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(rss_url, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code == 200:
                    feed = feedparser.parse(r.text)
                    # Filter for articles containing symbol in title/summary or just take latest
                    relevant_entries = []
                    for entry in feed.entries:
                        title = entry.get("title", "")
                        summary = entry.get("summary", "")
                        if symbol.lower() in title.lower() or symbol.lower() in summary.lower():
                            relevant_entries.append(title)
                    
                    # If we don't have enough specific to the symbol, backfill with general market news
                    if len(relevant_entries) < 5:
                        for entry in feed.entries:
                            title = entry.get("title", "")
                            if title not in relevant_entries:
                                relevant_entries.append(title)
                            if len(relevant_entries) >= 5:
                                break
                                
                    headlines = relevant_entries[:5]
        except Exception as e:
            headlines = [f"Failed to fetch news feed for {symbol}"]

    # 3. Compute Sentiment
    sentiment = calculate_sentiment(headlines)

    return {
        "symbol": symbol,
        "headlines": headlines,
        "sentiment_score": round(sentiment, 2),
        "fetched_at_ist": datetime.now(IST).isoformat(),
        "schema_version": "india-news-v1"
    }
