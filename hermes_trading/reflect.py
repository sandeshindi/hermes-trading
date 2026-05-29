import argparse
import yaml
import json
from pathlib import Path
from datetime import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")

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

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fallback", action="store_true")
    parser.add_argument("--hermes", action="store_true")
    args = parser.parse_args()
    
    if args.fallback:
        fallback_reflect()
