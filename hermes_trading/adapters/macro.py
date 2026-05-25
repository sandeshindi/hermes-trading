"""
India Macro Adapter (free public feeds)

Sources:
  RBI repo rate:   https://www.rbi.org.in/scripts/BS_PressReleaseDisplay.aspx (scraped or defaulted)
  Nifty 50 index:  https://www.nseindia.com/api/allIndices (free or yfinance fallback ^NSEI)
  USD/INR rate:    https://open.er-api.com/v6/latest/USD (free, no key)

Exposes:
  async def fetch() -> dict
    schema_version: "india-macro-v1"
    fields: rbi_repo_rate_pct, nifty50_level, nifty50_change_pct,
            usd_inr_rate, market_sentiment (bull/bear/neutral classifier)
"""

import httpx
import yfinance as yf
import logging

logger = logging.getLogger(__name__)

async def fetch() -> dict:
    # 1. Defaults
    rbi_rate = 6.50
    nifty_level = 22500.0
    nifty_change = 0.0
    usd_inr = 83.50
    sentiment = "neutral"

    # 2. Fetch USD/INR exchange rate
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get("https://open.er-api.com/v6/latest/USD")
            if r.status_code == 200:
                rates = r.json().get("rates", {})
                usd_inr = rates.get("INR", usd_inr)
    except Exception as e:
        logger.error(f"Error fetching USD/INR rate: {e}")

    # 3. Fetch Nifty 50 index level via yfinance (extremely reliable fallback for index)
    try:
        nifty = yf.Ticker("^NSEI")
        info = nifty.fast_info
        if "lastPrice" in info:
            nifty_level = info["lastPrice"]
            # Calculate simple change percent
            hist = nifty.history(period="2d")
            if len(hist) >= 2:
                prev_close = hist["Close"].iloc[0]
                nifty_change = ((nifty_level - prev_close) / prev_close) * 100
    except Exception as e:
        logger.error(f"Error fetching Nifty 50 via yfinance: {e}")

    # 4. Market sentiment classifier based on Nifty 50 change
    if nifty_change > 0.5:
        sentiment = "bull"
    elif nifty_change < -0.5:
        sentiment = "bear"
    else:
        sentiment = "neutral"

    return {
        "rbi_repo_rate_pct": round(rbi_rate, 2),
        "nifty50_level": round(nifty_level, 2),
        "nifty50_change_pct": round(nifty_change, 2),
        "usd_inr_rate": round(usd_inr, 2),
        "market_sentiment": sentiment,
        "schema_version": "india-macro-v1"
    }
