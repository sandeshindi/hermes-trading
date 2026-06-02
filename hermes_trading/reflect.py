import argparse
import yaml
import json
import os
from pathlib import Path
from datetime import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")

def load_env_if_local():
    try:
        from hermes_trading.run import load_dotenv
        load_dotenv()
    except Exception:
        pass

def fallback_reflect():
    from hermes_trading.config import get_state_dir
    state_path = get_state_dir()
    
    strategy_path = state_path / "strategy.yaml"
    history_dir = state_path / "history"
    hypotheses_path = state_path / "hypotheses.jsonl"
    
    with open(strategy_path, "r") as f:
        strategy = yaml.safe_load(f)
    
    old_version = strategy["version"]
    new_version = f"{int(old_version) + 1:02d}"
    
    # Save history
    history_path = history_dir / f"v{old_version}.yaml"
    with open(history_path, "w") as f:
        yaml.dump(strategy, f)
        
    # Dynamically resolve which variable to adjust based on active strategy features
    if "min_sentiment" in strategy.get("entry", {}):
        old_val = strategy["entry"]["min_sentiment"]
        new_val = round(old_val + 0.1, 2)  # Tighten sentiment filters to filter out risky trades
        strategy["entry"]["min_sentiment"] = new_val
        changed_var = "entry.min_sentiment"
        reason = "Increased news sentiment threshold to filter out low-confidence entries during down regimes."
    elif "threshold" in strategy.get("entry", {}):
        old_val = strategy["entry"]["threshold"]
        new_val = old_val - 2
        strategy["entry"]["threshold"] = new_val
        changed_var = "entry.threshold"
        reason = "Lowering entry threshold to adjust execution concurrency."
    else:
        old_val = strategy.get("stop_loss_pct", 2.0)
        new_val = round(old_val - 0.2, 2)  # Tighten stop-loss to reduce drawdowns
        strategy["stop_loss_pct"] = new_val
        changed_var = "stop_loss_pct"
        reason = "Tightening stop-loss limits to proactively defend capital against market volatility."
        
    strategy["version"] = new_version
    
    with open(strategy_path, "w") as f:
        yaml.dump(strategy, f)
        
    hypothesis = {
        "timestamp": datetime.now(IST).isoformat(),
        "version": new_version,
        "variable": changed_var,
        "old_value": old_val,
        "new_value": new_val,
        "reason": reason
    }
    
    with open(hypotheses_path, "a") as f:
        f.write(json.dumps(hypothesis) + "\n")
        
    print(f"Reflected: Strategy bumped to v{new_version}")

def hermes_reflect():
    import httpx
    
    load_env_if_local()
    
    from hermes_trading.config import get_state_dir
    state_path = get_state_dir()
    
    strategy_path = state_path / "strategy.yaml"
    goal_path = state_path / "goal.yaml"
    trades_path = state_path / "trades.jsonl"
    history_dir = state_path / "history"
    hypotheses_path = state_path / "hypotheses.jsonl"
    
    if not strategy_path.exists() or not goal_path.exists():
        print("Missing strategy.yaml or goal.yaml files.")
        return
        
    with open(strategy_path, "r") as f:
        strategy = yaml.safe_load(f)
    with open(goal_path, "r") as f:
        goal = yaml.safe_load(f)
        
    trades = []
    if trades_path.exists():
        with open(trades_path, "r") as f:
            for line in f:
                if line.strip():
                    trades.append(json.loads(line))
                    
    # Get last 25 trades
    last_trades = trades[-25:]
    
    old_version = strategy.get("version", "01")
    new_version = f"{int(old_version) + 1:02d}"
    
    # Check AI Provider
    provider = os.getenv("HERMES_PROVIDER", "google").lower()
    model_name = os.getenv("HERMES_MODEL", "gemini-2.5-flash")
    
    print(f">>> Launching AI reflection with {provider}/{model_name}...")
    
    prompt = f"""
You are Hermes, the self-improving quantitative stock trading agent.
Your goal is to optimize the current trading strategy based on past trade performance.

Strategy Goal:
{yaml.dump(goal)}

Current Strategy (v{old_version}):
{yaml.dump(strategy)}

Last 25 Trades:
{json.dumps(last_trades, indent=2) if last_trades else "No trades completed yet. Optimize based on initial state/assumptions."}

Scientific Method Guardrails:
1. You MUST change exactly ONE variable in strategy.yaml.
2. The allowed variables to modify are:
   - `entry.min_sentiment` (news filter, float, e.g. 0.1 to 0.9)
   - `entry.threshold` (RSI or indicator trigger threshold, e.g. 20 to 50)
   - `stop_loss_pct` (fixed stop-loss, float, e.g. 1.0 to 5.0)
   - `atr_multiplier` (ATR exit multiplier, float, e.g. 1.5 to 4.0)
   - `position_size_r` (risk fraction per trade, float, e.g. 0.1 to 1.0)
   - `holding_period_days` (holding settlement swing, int, e.g. 1 to 10)
3. You must explain your scientific hypothesis (why this change will improve the return/drawdown metric).

Respond strictly in valid JSON format. Do not wrap in backticks or markdown code block formats.
The response must follow this schema:
{{
  "variable": "the_exact_variable_name_you_changed",
  "old_value": old_value,
  "new_value": new_value,
  "reason": "Clear explanation of the hypothesis behind this adjustment.",
  "updated_strategy": {{
     // The entire strategy dictionary with ONLY the one variable changed and version bumped to "{new_version}"
  }}
}}
"""

    resp_json = None
    
    if provider == "google":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("GEMINI_API_KEY is not set.")
            return
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"}
        }
        try:
            r = httpx.post(url, headers=headers, json=payload, timeout=45.0)
            if r.status_code == 200:
                text_content = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                resp_json = json.loads(text_content.strip())
            else:
                print(f"Gemini API returned status {r.status_code}: {r.text}")
                return
        except Exception as e:
            print(f"Error calling Gemini: {e}")
            return
            
    elif provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            print("ANTHROPIC_API_KEY is not set.")
            return
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        payload = {
            "model": model_name,
            "max_tokens": 1500,
            "messages": [{"role": "user", "content": prompt + "\nProvide only the raw JSON. No markdown code blocks."}]
        }
        try:
            r = httpx.post(url, headers=headers, json=payload, timeout=45.0)
            if r.status_code == 200:
                text_content = r.json()["content"][0]["text"].strip()
                if text_content.startswith("```"):
                    text_content = text_content.split("```")[1]
                    if text_content.startswith("json"):
                        text_content = text_content[4:]
                resp_json = json.loads(text_content.strip())
            else:
                print(f"Claude API returned status {r.status_code}: {r.text}")
                return
        except Exception as e:
            print(f"Error calling Claude: {e}")
            return
            
    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("OPENAI_API_KEY is not set.")
            return
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
            r = httpx.post(url, headers=headers, json=payload, timeout=45.0)
            if r.status_code == 200:
                text_content = r.json()["choices"][0]["message"]["content"]
                resp_json = json.loads(text_content.strip())
            else:
                print(f"OpenAI API returned status {r.status_code}: {r.text}")
                return
        except Exception as e:
            print(f"Error calling OpenAI: {e}")
            return
    else:
        print(f"Unsupported provider: {provider}")
        return

    if not resp_json:
        print("Empty or invalid response from AI model.")
        return

    # Extract results
    changed_var = resp_json.get("variable", "unknown")
    old_val = resp_json.get("old_value")
    new_val = resp_json.get("new_value")
    reason = resp_json.get("reason", "AI reflection adjustment")
    updated_strat = resp_json.get("updated_strategy")
    
    if not updated_strat:
        print("AI response missing updated_strategy.")
        return

    # Ensure version is correct
    updated_strat["version"] = new_version
    
    # Save historical version
    history_path = history_dir / f"v{old_version}.yaml"
    with open(history_path, "w") as f:
        yaml.dump(strategy, f)

    # Save new strategy.yaml
    with open(strategy_path, "w") as f:
        yaml.dump(updated_strat, f)

    # Log to hypotheses.jsonl
    hypothesis = {
        "timestamp": datetime.now(IST).isoformat(),
        "version": new_version,
        "variable": changed_var,
        "old_value": old_val,
        "new_value": new_val,
        "reason": reason
    }
    
    with open(hypotheses_path, "a") as f:
        f.write(json.dumps(hypothesis) + "\n")
        
    print(f"Reflected: Strategy successfully evolved and bumped to v{new_version} via AI optimization!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fallback", action="store_true")
    parser.add_argument("--hermes", action="store_true")
    args = parser.parse_args()
    
    if args.fallback:
        fallback_reflect()
    elif args.hermes:
        hermes_reflect()
