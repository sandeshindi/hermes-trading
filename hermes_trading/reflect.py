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
        
    # Apply a dummy change for demonstration
    old_val = strategy["entry"]["threshold"]
    new_val = old_val - 2
    strategy["entry"]["threshold"] = new_val
    strategy["version"] = new_version
    
    with open(strategy_path, "w") as f:
        yaml.dump(strategy, f)
        
    hypothesis = {
        "timestamp": datetime.now(IST).isoformat(),
        "version": new_version,
        "variable": "entry.threshold",
        "old_value": old_val,
        "new_value": new_val,
        "reason": "Lowering threshold to increase entry frequency based on initial data."
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
