import asyncio
import argparse
import yaml
import os
from pathlib import Path
from datetime import datetime
import pytz
from hermes_trading.loop import trading_loop
from hermes_trading.dashboard import start_dashboard

def load_goal():
    with open("state/goal.yaml", "r") as f:
        return yaml.safe_load(f)

async def main():
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
