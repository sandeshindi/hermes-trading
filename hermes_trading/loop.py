import asyncio
import json
import yaml
import os
import math
from datetime import datetime, timedelta
import pytz
from pathlib import Path
import yfinance as yf
import pandas as pd
import httpx
from hermes_trading.adapters import news, macro, fundamentals

IST = pytz.timezone("Asia/Kolkata")
last_ai_queries = {}
last_global_ai_query_time = None
rate_limit_penalty_until = None

async def get_market_data(asset):
    # Fetch 5 days of 15m data to have enough periods for all indicators
    symbol = f"{asset}.NS"
    ticker = yf.Ticker(symbol)
    data = ticker.history(period="5d", interval="15m")
    
    if data.empty or len(data) < 26: # Need at least 26 periods for EMAs/Bands
        return None
        
    close_prices = data['Close']
    price = float(close_prices.iloc[-1])
    
    # 1. Calculate RSI (14 period)
    delta = close_prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    current_rsi = float(rsi.iloc[-1])
    if pd.isna(current_rsi):
        current_rsi = 50.0
        
    # 2. Calculate SMAs (9-period and 21-period SMA)
    sma_9 = float(close_prices.rolling(window=9).mean().iloc[-1])
    sma_21 = float(close_prices.rolling(window=21).mean().iloc[-1])
    
    # 3. Calculate MACD & Signal Line
    ema_12 = close_prices.ewm(span=12, adjust=False).mean()
    ema_26 = close_prices.ewm(span=26, adjust=False).mean()
    macd_series = ema_12 - ema_26
    signal_series = macd_series.ewm(span=9, adjust=False).mean()
    current_macd = float(macd_series.iloc[-1])
    current_signal = float(signal_series.iloc[-1])
    
    # 4. Calculate Bollinger Bands (20-period SMA)
    sma_20 = close_prices.rolling(window=20).mean()
    std_20 = close_prices.rolling(window=20).std()
    bb_upper = sma_20 + 2 * std_20
    bb_lower = sma_20 - 2 * std_20
    current_bb_upper = float(bb_upper.iloc[-1])
    current_bb_lower = float(bb_lower.iloc[-1])
    
    # 5. Calculate ATR (14-period Average True Range)
    high = data['High']
    low = data['Low']
    prev_close = close_prices.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr_series = tr.rolling(window=14).mean()
    current_atr = float(atr_series.iloc[-1])
    
    return {
        "price": price,
        "rsi": current_rsi,
        "sma_9": sma_9,
        "sma_21": sma_21,
        "macd": current_macd,
        "signal": current_signal,
        "bb_upper": current_bb_upper,
        "bb_lower": current_bb_lower,
        "atr": current_atr
    }

async def get_ai_decision(asset, price, indicators, news_data, fundamentals_data, macro_data) -> dict:
    """Queries live Google Gemini, Anthropic Claude, or OpenAI API to make trading decisions."""
    provider = os.getenv("HERMES_PROVIDER", "google").lower()
    
    # Format news list
    headlines_str = "\n".join(f"- {h}" for h in news_data.get("headlines", [])) if news_data else "No news available"
    
    prompt = f"""
You are an expert quantitative swing trader specializing in Indian Equities (NSE).
Analyze the following live market dataset for {asset} and decide whether to BUY, SELL, or HOLD.

Market Data for {asset}:
- Current Price: INR {price:.2f}
- RSI (14-period): {indicators.get('rsi', 50):.1f}
- SMA 9: {indicators.get('sma_9', price):.1f}
- SMA 21: {indicators.get('sma_21', price):.1f}
- MACD: {indicators.get('macd', 0):+.2f} | Signal: {indicators.get('signal', 0):+.2f}
- Bollinger Bands: Lower = {indicators.get('bb_lower', price):.1f} | Upper = {indicators.get('bb_upper', price):.1f}
- ATR (14-period): {indicators.get('atr', 0):.2f}

Fundamentals Data:
- P/E Ratio: {fundamentals_data.get('pe_ratio', 'N/A')}
- P/B Ratio: {fundamentals_data.get('pb_ratio', 'N/A')}
- EPS: {fundamentals_data.get('eps', 'N/A')}

News Sentiment:
- Computed Sentiment Score (-1 to +1): {news_data.get('sentiment_score', 0.0) if news_data else 0.0:+.2f}
- Recent Headlines:
{headlines_str}

Macro Regime:
- Nifty 50 Level: {macro_data.get('nifty50_level', 'N/A')}
- Nifty daily change: {macro_data.get('nifty50_change_pct', 0.0):+.2f}%
- Market Sentiment Class: {macro_data.get('market_sentiment', 'neutral')}
- USD/INR Rate: {macro_data.get('usd_inr_rate', 'N/A')}

Constraints:
1. Trade long only.
2. Ensure you have a clear reason based on technical confluence, corporate fundamentals, and news sentiment.

Respond strictly in valid JSON format. Do not wrap in backticks or markdown code block formats.
The JSON must follow this schema:
{
  "decision": "BUY" | "SELL" | "HOLD",
  "conviction_score": 1-10, // Integer conviction rating (1 is lowest conviction, 10 is absolute highest conviction)
  "reason": "Provide a concise explanation of why this decision was chosen."
}
"""

    if provider == "google":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return {"decision": "HOLD", "reason": "GEMINI_API_KEY is not set in environment."}
        model_name = os.getenv("HERMES_MODEL", "gemini-2.5-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"}
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.post(url, headers=headers, json=payload)
                if r.status_code == 200:
                    resp_json = r.json()
                    text_content = resp_json["candidates"][0]["content"]["parts"][0]["text"]
                    return json.loads(text_content.strip())
                else:
                    return {"decision": "HOLD", "reason": f"Gemini API returned status {r.status_code}: {r.text}"}
        except Exception as e:
            return {"decision": "HOLD", "reason": f"Error calling Gemini: {e}"}

    elif provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return {"decision": "HOLD", "reason": "ANTHROPIC_API_KEY is not set in environment."}
        model_name = os.getenv("HERMES_MODEL", "claude-3-5-sonnet-20241022")
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        payload = {
            "model": model_name,
            "max_tokens": 1000,
            "messages": [{"role": "user", "content": prompt + "\nProvide only the raw JSON. No markdown code blocks."}]
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.post(url, headers=headers, json=payload)
                if r.status_code == 200:
                    text_content = r.json()["content"][0]["text"]
                    clean_text = text_content.strip()
                    if clean_text.startswith("```"):
                        clean_text = clean_text.split("```")[1]
                        if clean_text.startswith("json"):
                            clean_text = clean_text[4:]
                    return json.loads(clean_text.strip())
                else:
                    return {"decision": "HOLD", "reason": f"Claude API returned status {r.status_code}: {r.text}"}
        except Exception as e:
            return {"decision": "HOLD", "reason": f"Error calling Claude: {e}"}

    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return {"decision": "HOLD", "reason": "OPENAI_API_KEY is not set in environment."}
        model_name = os.getenv("HERMES_MODEL", "gpt-4o-mini")
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"}
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.post(url, headers=headers, json=payload)
                if r.status_code == 200:
                    text_content = r.json()["choices"][0]["message"]["content"]
                    return json.loads(text_content.strip())
                else:
                    return {"decision": "HOLD", "reason": f"OpenAI API returned status {r.status_code}: {r.text}"}
        except Exception as e:
            return {"decision": "HOLD", "reason": f"Error calling OpenAI: {e}"}

    else:
        return {"decision": "HOLD", "reason": f"Unsupported AI provider specified: {provider}"}

def is_market_open(market_hours):
    now = datetime.now(IST)
    if now.weekday() >= 5: # Weekend
        return False
    
    start_str, end_str = market_hours.split("-")
    start_time = datetime.strptime(start_str.strip(), "%H:%M").time()
    end_time = datetime.strptime(end_str.split()[0].strip(), "%H:%M").time()
    
    current_time = now.time()
    return start_time <= current_time <= end_time

def load_yaml(path):
    if not path.exists():
        return {}
    with open(path, "r") as f:
        return yaml.safe_load(f)

def save_yaml(path, data):
    with open(path, "w") as f:
        yaml.dump(data, f)

async def trading_loop(assets, goal):
    from hermes_trading.config import get_state_dir
    state_path = get_state_dir()
    heartbeat_path = state_path / "heartbeat.json"
    trades_path = state_path / "trades.jsonl"
    strategy_path = state_path / "strategy.yaml"
    goal_path = state_path / "goal.yaml"

    open_positions = {}
    global last_global_ai_query_time
    global rate_limit_penalty_until
    latest_prices = {}
    
    # Pre-load existing open trades from file to memory
    if trades_path.exists():
        with open(trades_path, "r") as f:
            for line in f:
                if line.strip():
                    t = json.loads(line)
                    asset = t.get("asset")
                    if t.get("status") == "open":
                        open_positions[asset] = t
                    elif t.get("status") == "closed" and asset in open_positions:
                        del open_positions[asset]

    while True:
        now = datetime.now(IST)
        # Reload goal to get latest capital
        goal = load_yaml(goal_path)
        current_assets = goal.get("assets", assets)
        market_open = is_market_open(goal.get("market_hours", "09:15-15:30 IST"))
        
        heartbeat = {
            "timestamp": now.isoformat(),
            "market_status": "open" if market_open else "closed"
        }
        
        with open(heartbeat_path, "w") as f:
            json.dump(heartbeat, f)

        if market_open:
            strategy = load_yaml(strategy_path)
            rsi_threshold = strategy.get("entry", {}).get("threshold", 30)
            stop_loss_pct = strategy.get("stop_loss_pct", 2.0)
            position_size_r = strategy.get("position_size_r", 0.5)
            
            # Fetch macro data once per loop iteration if strategy requires it OR if indicator is AI
            macro_data = None
            avoid_bear = strategy.get("avoid_bear_regimes", False) or strategy.get("entry", {}).get("avoid_bear_regimes", False)
            indicator_type = strategy.get("entry", {}).get("indicator", "rsi")
            if avoid_bear or indicator_type == "ai":
                try:
                    macro_data = await macro.fetch()
                except Exception as e:
                    print(f"Error fetching macro data: {e}")
            
            for asset in current_assets:
                conviction_score = 5
                market_data = await get_market_data(asset)
                if market_data:
                    price = market_data["price"]
                    rsi = market_data["rsi"]
                    sma_9 = market_data["sma_9"]
                    sma_21 = market_data["sma_21"]
                    macd_val = market_data["macd"]
                    signal_val = market_data["signal"]
                    bb_upper = market_data["bb_upper"]
                    bb_lower = market_data["bb_lower"]
                    atr_val = market_data["atr"]
                    
                    # Update prices cache file for the dashboard
                    latest_prices[asset] = {
                        "price": price,
                        "rsi": rsi,
                        "timestamp": now.strftime('%H:%M:%S'),
                        "ai_decision": "SCANNING",
                        "ai_reason": "Waiting for AI consult or indicators threshold..."
                    }
                    try:
                        with open(state_path / "prices.json", "w") as pf:
                            json.dump(latest_prices, pf)
                    except Exception:
                        pass
                    
                    # Print standard info with dynamic metrics based on strategy
                    log_msg = f"[{now.strftime('%H:%M:%S')}] {asset} | Price: Rs.{price:.2f}"
                    indicator_type = strategy.get("entry", {}).get("indicator", "rsi")
                    if indicator_type == "rsi":
                        log_msg += f" | RSI: {rsi:.1f}"
                    elif indicator_type == "sma_cross":
                        log_msg += f" | SMA9: {sma_9:.1f} | SMA21: {sma_21:.1f}"
                    elif indicator_type == "macd":
                        log_msg += f" | MACD: {macd_val:+.2f} | Signal: {signal_val:+.2f}"
                    elif indicator_type == "bollinger":
                        log_msg += f" | BB Lower: {bb_lower:.1f} | BB Upper: {bb_upper:.1f}"
                    elif indicator_type == "ai":
                        log_msg += f" | RSI: {rsi:.1f} | MACD: {macd_val:+.2f}"
                        
                    log_msg += f" | ATR: {atr_val:.2f}"
                    
                    # Fetch and log news sentiment if strategy requires it OR if indicator is AI
                    news_data = None
                    min_sentiment = strategy.get("entry", {}).get("min_sentiment")
                    if min_sentiment is not None or indicator_type == "ai":
                        try:
                            news_data = await news.fetch(asset)
                            sentiment = news_data.get("sentiment_score", 0.0)
                            log_msg += f" | News Sentiment: {sentiment:+.2f}"
                            if min_sentiment is not None:
                                log_msg += f" (Min: {min_sentiment:+.2f})"
                        except Exception as e:
                            print(f"Error fetching news: {e}")
                            
                    # Fetch fundamentals if indicator is AI
                    fundamentals_data = {}
                    if indicator_type == "ai":
                        try:
                            fundamentals_data = await fundamentals.fetch(asset)
                        except Exception as e:
                            print(f"Error fetching fundamentals: {e}")
                            
                    if macro_data:
                        log_msg += f" | Nifty Regime: {macro_data.get('market_sentiment', 'unknown')}"
                        
                    print(log_msg)
                    
                    if asset in open_positions:
                        # EXIT LOGIC
                        pos = open_positions[asset]
                        latest_prices[asset]["ai_decision"] = "HOLDING"
                        latest_prices[asset]["ai_reason"] = f"Open trade (Qty: {pos['quantity']} @ ₹{pos['entry_price']:.2f}). Monitoring stop-loss & take-profit targets."
                        try:
                            with open(state_path / "prices.json", "w") as pf:
                                json.dump(latest_prices, pf)
                        except Exception:
                            pass
                        
                        entry_price = pos["entry_price"]
                        
                        # Stop Loss and Take Profit levels
                        sl_mode = strategy.get("stop_loss_mode", "fixed")
                        
                        if sl_mode == "atr":
                            multiplier = strategy.get("atr_multiplier", 2.0)
                            sl_price = entry_price - (multiplier * atr_val)
                            tp_price = entry_price + (multiplier * 2.0 * atr_val)
                        else:
                            sl_price = entry_price * (1 - (stop_loss_pct / 100))
                            tp_price = entry_price * (1 + (stop_loss_pct * 2 / 100))
                        
                        if price <= sl_price or price >= tp_price:
                            qty = pos["quantity"]
                            pnl = (price - entry_price) * qty
                            
                            # Close position
                            pos["status"] = "closed"
                            pos["exit_price"] = price
                            pos["exit_time"] = now.strftime('%Y-%m-%d %H:%M:%S')
                            pos["pnl_inr"] = round(pnl, 2)
                            
                            print(f">>> CLOSED {asset} Trade: PnL Rs.{pnl:.2f}")
                            
                            # Update Capital
                            goal["current_capital_inr"] += pnl
                            save_yaml(goal_path, goal)
                            
                            # Log to trades
                            with open(trades_path, "a") as f:
                                f.write(json.dumps(pos) + "\n")
                                
                            del open_positions[asset]
                            
                            # Check if we should trigger an automatic reflection cycle!
                            try:
                                closed_count = 0
                                if trades_path.exists():
                                    with open(trades_path, "r") as tf:
                                        for line in tf:
                                            if line.strip():
                                                trade_obj = json.loads(line)
                                                if trade_obj.get("status") == "closed":
                                                    closed_count += 1
                                
                                reflection_cadence = goal.get("reflection_every", 5)
                                if closed_count > 0 and closed_count % reflection_cadence == 0:
                                    print(f">>> [Auto-Reflection] Closed trades count ({closed_count}) is a multiple of {reflection_cadence}. Launching strategy updates...")
                                    import subprocess
                                    import sys
                                    import os
                                    reflect_mode = "--hermes" if os.getenv("HERMES_REFLECT_MODE") == "hermes" else "--fallback"
                                    subprocess.Popen([sys.executable, "-m", "hermes_trading.reflect", reflect_mode])
                            except Exception as re:
                                print(f"Error checking/triggering automatic reflection: {re}")
                            
                    else:
                        # ENTRY LOGIC
                        # 1. Technical Indicator Condition (RSI, SMA, MACD, Bollinger Bands, or Gemini AI Decision)
                        tech_condition = False
                        indicator_type = strategy.get("entry", {}).get("indicator", "rsi")
                        
                        if indicator_type == "rsi":
                            tech_condition = rsi < rsi_threshold
                        elif indicator_type == "sma_cross":
                            # Buy when short-term SMA9 is above long-term SMA21 (Bullish Golden Cross)
                            tech_condition = sma_9 > sma_21
                        elif indicator_type == "macd":
                            # Buy when MACD crosses above Signal line
                            tech_condition = macd_val > signal_val
                        elif indicator_type == "bollinger":
                            # Buy when price crosses below or touches Lower Band
                            tech_condition = price <= bb_lower
                        elif indicator_type == "ai":
                            # 0. Global Rate Limit Penalty check: If Google AI Studio rate limit is hit, do not call AI
                            if rate_limit_penalty_until and now < rate_limit_penalty_until:
                                time_left = (rate_limit_penalty_until - now).total_seconds()
                                print(f"[{now.strftime('%H:%M:%S')}] {asset} | Rate Limit Penalty Active: Skipping AI query to allow quota recovery ({time_left:.0f}s left).")
                                tech_condition = False
                                latest_prices[asset]["ai_decision"] = "PENALTY"
                                latest_prices[asset]["ai_reason"] = f"Rate Limit Penalty: Active until {rate_limit_penalty_until.strftime('%H:%M:%S')} to allow quota reset."
                                try:
                                    with open(state_path / "prices.json", "w") as pf:
                                        json.dump(latest_prices, pf)
                                except Exception:
                                    pass
                            # 1. Technical Pre-filtering: Only consult the AI model if RSI is reasonably cool (RSI < 55)
                            # This saves significant API quota by ignoring clearly overbought assets.
                            elif rsi >= 55:
                                print(f"[{now.strftime('%H:%M:%S')}] {asset} | Pre-filtered: RSI ({rsi:.1f}) >= 55 is overbought. Skipping AI query.")
                                tech_condition = False
                                latest_prices[asset]["ai_decision"] = "SKIP"
                                latest_prices[asset]["ai_reason"] = f"RSI ({rsi:.1f}) >= 55 is overbought (Pre-filtered)."
                                try:
                                    with open(state_path / "prices.json", "w") as pf:
                                        json.dump(latest_prices, pf)
                                except Exception:
                                    pass
                            else:
                                # 2. 15-Minute AI Cooldown: Avoid spamming the model every minute for the same asset
                                cooldown_key = f"{asset}_entry"
                                last_query_time = last_ai_queries.get(cooldown_key)
                                
                                # 3. Global AI Cooldown: Stagger queries globally by at least 30s to stay safely under RPM limits
                                time_since_last_global = (now - last_global_ai_query_time).total_seconds() if last_global_ai_query_time else 9999.0
                                
                                if last_query_time and (now - last_query_time).total_seconds() < 900:
                                    print(f"[{now.strftime('%H:%M:%S')}] {asset} | AI Cooldown: Asked less than 15m ago. Skipping AI query.")
                                    tech_condition = False
                                    latest_prices[asset]["ai_decision"] = "COOLDOWN"
                                    latest_prices[asset]["ai_reason"] = "Individual asset cooldown: asked AI less than 15m ago."
                                    try:
                                        with open(state_path / "prices.json", "w") as pf:
                                            json.dump(latest_prices, pf)
                                    except Exception:
                                        pass
                                elif time_since_last_global < 30:
                                    print(f"[{now.strftime('%H:%M:%S')}] {asset} | Global AI Cooldown: Last query was {time_since_last_global:.1f}s ago. Staggering to prevent rate limit.")
                                    tech_condition = False
                                    latest_prices[asset]["ai_decision"] = "STAGGERED"
                                    latest_prices[asset]["ai_reason"] = f"Staggering active. Last query was {time_since_last_global:.1f}s ago."
                                    try:
                                        with open(state_path / "prices.json", "w") as pf:
                                            json.dump(latest_prices, pf)
                                    except Exception:
                                        pass
                                else:
                                    # Query live Gemini AI decision model
                                    ai_decision = await get_ai_decision(asset, price, market_data, news_data, fundamentals_data, macro_data)
                                    last_ai_queries[cooldown_key] = now
                                    last_global_ai_query_time = now
                                    decision = ai_decision.get("decision", "HOLD")
                                    reason = ai_decision.get("reason", "No reason provided.")
                                    try:
                                        conviction_score = int(ai_decision.get("conviction_score", 5))
                                    except Exception:
                                        conviction_score = 5
                                    print(f">>> [Gemini AI Decision] {asset}: {decision} (Score: {conviction_score}) | Reason: {reason}")
                                    tech_condition = (decision == "BUY")
                                    
                                    # Check if rate limited (status 429)
                                    if "429" in reason or "quota" in reason.lower() or "limit" in reason.lower():
                                        rate_limit_penalty_until = now + timedelta(minutes=3)
                                        print(f">>> [Rate Limit Alert] 429 detected. Setting global penalty active until {rate_limit_penalty_until.strftime('%H:%M:%S')}.")
                                        latest_prices[asset]["ai_decision"] = "PENALTY"
                                        latest_prices[asset]["ai_reason"] = f"Gemini Rate Limit (429) Hit. Cool-off penalty active until {rate_limit_penalty_until.strftime('%H:%M:%S')}."
                                    else:
                                        latest_prices[asset]["ai_decision"] = decision
                                        latest_prices[asset]["ai_reason"] = reason
                                        
                                    try:
                                        with open(state_path / "prices.json", "w") as pf:
                                            json.dump(latest_prices, pf)
                                    except Exception:
                                        pass
                        
                        # 2. News Sentiment Condition (if configured)
                        news_condition = True
                        if min_sentiment is not None and news_data is not None:
                            news_condition = news_data.get("sentiment_score", 0.0) >= min_sentiment
                            
                        # 3. Macro Regime Condition (if configured)
                        macro_condition = True
                        if avoid_bear and macro_data is not None:
                            macro_condition = macro_data.get("market_sentiment") != "bear"
                            
                        if tech_condition and news_condition and macro_condition:
                            max_active = strategy.get("max_active_positions", 3)
                            if len(open_positions) >= max_active:
                                enable_rotation = strategy.get("enable_rotation", False)
                                rotation_score_diff = strategy.get("rotation_score_diff", 3)
                                
                                rotated = False
                                if enable_rotation and len(open_positions) > 0:
                                    # Find the open position with the lowest conviction score
                                    lowest_asset = min(
                                        open_positions.keys(),
                                        key=lambda a: open_positions[a].get("conviction_score", 5)
                                    )
                                    lowest_score = open_positions[lowest_asset].get("conviction_score", 5)
                                    
                                    # If the new asset conviction score is better by the required threshold
                                    if conviction_score - lowest_score >= rotation_score_diff:
                                        print(f">>> [Rotation] {asset} (Score: {conviction_score}) is better than held {lowest_asset} (Score: {lowest_score}) by >= {rotation_score_diff}. Swapping...")
                                        
                                        # Fetch market price of the asset being sold/closed
                                        lowest_market_data = await get_market_data(lowest_asset)
                                        if lowest_market_data:
                                            low_price = lowest_market_data["price"]
                                            low_pos = open_positions[lowest_asset]
                                            qty_to_sell = low_pos["quantity"]
                                            entry_p = low_pos["entry_price"]
                                            pnl = (low_price - entry_p) * qty_to_sell
                                            
                                            # Close position details
                                            low_pos["status"] = "closed"
                                            low_pos["exit_price"] = low_price
                                            low_pos["exit_time"] = now.strftime('%Y-%m-%d %H:%M:%S')
                                            low_pos["pnl_inr"] = round(pnl, 2)
                                            
                                            # Update Capital
                                            goal["current_capital_inr"] += pnl
                                            save_yaml(goal_path, goal)
                                            
                                            # Log closed trade to trades file
                                            with open(trades_path, "a") as f:
                                                f.write(json.dumps(low_pos) + "\n")
                                                
                                            del open_positions[lowest_asset]
                                            print(f">>> ROTATED OUT {lowest_asset} @ Rs.{low_price:.2f} | PnL: Rs.{pnl:.2f}")
                                            rotated = True
                                        else:
                                            print(f"Failed to fetch price for {lowest_asset} during swap. Aborting rotation.")
                                            
                                if not rotated:
                                    print(f"[{now.strftime('%H:%M:%S')}] Signal triggered for {asset} but skipped: max active positions slot capacity ({max_active}) reached and rotation not applicable.")
                                    continue
                            
                            capital = goal.get("current_capital_inr", 50000)
                            asset_capital = capital / max_active
                            investment = asset_capital * position_size_r
                            qty = math.floor(investment / price)
                            
                            if qty > 0:
                                new_trade = {
                                    "asset": asset,
                                    "side": "BUY",
                                    "status": "open",
                                    "entry_price": price,
                                    "quantity": qty,
                                    "entry_time": now.strftime('%Y-%m-%d %H:%M:%S'),
                                    "conviction_score": conviction_score
                                }
                                open_positions[asset] = new_trade
                                print(f">>> OPENED {asset} Trade: {qty} shares @ Rs.{price:.2f} | Conviction: {conviction_score}")
                                
                                # Log to trades
                                with open(trades_path, "a") as f:
                                    f.write(json.dumps(new_trade) + "\n")

                else:
                    print(f"[{now.strftime('%H:%M:%S')}] Failed to fetch price for {asset}")
        else:
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Market Closed. Sleeping...")

        await asyncio.sleep(60)
