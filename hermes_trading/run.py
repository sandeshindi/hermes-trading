import asyncio
import argparse
import yaml
import os
from pathlib import Path
from datetime import datetime
import pytz
from hermes_trading.loop import trading_loop
from hermes_trading.dashboard import start_dashboard

def load_dotenv(env_path=".env"):
    path = Path(env_path)
    if not path.exists():
        return
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                # Handle inline comments
                if "#" in val:
                    if val.startswith('"'):
                        idx = val.find('"', 1)
                        if idx != -1:
                            val = val[:idx+1]
                    elif val.startswith("'"):
                        idx = val.find("'", 1)
                        if idx != -1:
                            val = val[:idx+1]
                    else:
                        val = val.split("#", 1)[0].strip()
                # Strip surrounding quotes
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                os.environ[key] = val

def load_goal():
    with open("state/goal.yaml", "r") as f:
        return yaml.safe_load(f)

async def main():
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", type=str, help="Comma-separated list of assets")
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()

    goal = load_goal()
    assets_str = args.assets or ", ".join(goal.get("assets", []))
    assets = [a.strip() for a in assets_str.split(",") if a.strip()]
    
    print(f"Starting Hermes Trading Agent for {assets}...")
    
    # Start dashboard
    dashboard_task = asyncio.create_task(start_dashboard())
    
    # Start trading loop
    await trading_loop(assets, goal)

if __name__ == "__main__":
    asyncio.run(main())
