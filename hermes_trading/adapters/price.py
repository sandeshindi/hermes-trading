"""
Groww NSE Price Adapter

Primary:  Groww API  → https://api.groww.in/v1/api/stocks/  (requires GROWW_API_KEY)
Fallback: yfinance / NSE public data feed  → https://www.nseindia.com/api/quote-equity?symbol={SYMBOL}

Exposes:
  async def fetch(symbol: str) -> dict
    schema_version: "nse-price-v1"
    fields: symbol, ltp (last traded price INR), open, high, low, close,
            volume, timestamp_ist, change_pct, week_52_high, week_52_low
"""

import os
import httpx
import yfinance as yf
from datetime import datetime
import pytz
import logging

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

class SchemaError(Exception):
    """Raised when there is a schema mismatch in returned api data."""
    pass

async def fetch(symbol: str) -> dict:
    api_key = os.getenv("GROWW_API_KEY")
    
    # 1. Try Primary: Groww API (if configured)
    if api_key:
        try:
            url = f"https://api.groww.in/v1/api/stocks/{symbol}"
            headers = {"Authorization": f"Bearer {api_key}"}
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(url, headers=headers)
                if r.status_code == 200:
                    data = r.json()
                    # Validate schema
                    required = ["ltp", "open", "high", "low", "close"]
                    if not all(k in data for k in required):
                        raise SchemaError(f"Groww response missing required fields for {symbol}")
                    
                    return {
                        "symbol": symbol,
                        "ltp": float(data["ltp"]),
                        "open": float(data["open"]),
                        "high": float(data["high"]),
                        "low": float(data["low"]),
                        "close": float(data["close"]),
                        "volume": int(data.get("volume", 0)),
                        "timestamp_ist": datetime.now(IST).isoformat(),
                        "change_pct": float(data.get("change_pct", 0.0)),
                        "week_52_high": float(data.get("week_52_high", data["high"])),
                        "week_52_low": float(data.get("week_52_low", data["low"])),
                        "schema_version": "nse-price-v1"
                    }
        except SchemaError as se:
            logger.error(f"Schema error in Groww API: {se}")
            raise se
        except Exception as e:
            logger.warning(f"Groww API failed for {symbol}, falling back to yfinance: {e}")

    # 2. Fallback: yfinance
    try:
        yf_symbol = f"{symbol}.NS"
        ticker = yf.Ticker(yf_symbol)
        info = ticker.fast_info
        
        # Verify schema/info properties
        if "lastPrice" not in info:
            raise SchemaError(f"yfinance missing price info for {yf_symbol}")
            
        hist = ticker.history(period="1d")
        day_open = float(hist["Open"].iloc[0]) if not hist.empty else float(info.get("open", info["lastPrice"]))
        day_high = float(hist["High"].iloc[0]) if not hist.empty else float(info.get("dayHigh", info["lastPrice"]))
        day_low = float(hist["Low"].iloc[0]) if not hist.empty else float(info.get("dayLow", info["lastPrice"]))
        day_close = float(hist["Close"].iloc[0]) if not hist.empty else float(info.get("previousClose", info["lastPrice"]))
        
        return {
            "symbol": symbol,
            "ltp": float(info["lastPrice"]),
            "open": day_open,
            "high": day_high,
            "low": day_low,
            "close": day_close,
            "volume": int(info.get("lastVolume", 0)),
            "timestamp_ist": datetime.now(IST).isoformat(),
            "change_pct": round(((info["lastPrice"] - day_close) / day_close) * 100, 2) if day_close else 0.0,
            "week_52_high": float(info.get("yearHigh", day_high)),
            "week_52_low": float(info.get("yearLow", day_low)),
            "schema_version": "nse-price-v1"
        }
    except Exception as e:
        logger.error(f"yfinance fallback failed for {symbol}: {e}")
        raise SchemaError(f"All price fetch methods failed for {symbol}: {e}")
