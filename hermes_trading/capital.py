import json
import yaml
import sys
import argparse
from pathlib import Path
from datetime import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")

def add_funds(amount: float, update_starting_capital: bool = True, note: str = "") -> dict:
    """
    Adds amount (in INR) to portfolio capital.
    - Updates current_capital_inr so subsequent trades automatically size larger volumes.
    - Optionally updates starting_capital_inr to maintain accurate ROI and drawdown percentages.
    - Records the deposit in capital_history.jsonl.
    """
    if amount <= 0:
        raise ValueError(f"Deposit amount must be positive. Received: {amount}")

    from hermes_trading.config import get_state_dir
    state_path = get_state_dir()
    goal_path = state_path / "goal.yaml"
    history_path = state_path / "capital_history.jsonl"

    if not goal_path.exists():
        raise FileNotFoundError(f"Goal file not found at {goal_path}")

    goal = yaml.safe_load(goal_path.read_text()) or {}
    
    old_current = float(goal.get("current_capital_inr", 50000))
    old_starting = float(goal.get("starting_capital_inr", 50000))
    
    new_current = round(old_current + amount, 2)
    new_starting = round(old_starting + amount, 2) if update_starting_capital else old_starting

    goal["current_capital_inr"] = new_current
    if update_starting_capital:
        goal["starting_capital_inr"] = new_starting

    goal_path.write_text(yaml.safe_dump(goal, sort_keys=False))

    now = datetime.now(IST)
    deposit_record = {
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S IST"),
        "type": "deposit",
        "amount": round(amount, 2),
        "old_current_capital": old_current,
        "new_current_capital": new_current,
        "old_starting_capital": old_starting,
        "new_starting_capital": new_starting,
        "update_starting_capital": update_starting_capital,
        "note": note or "Portfolio capital top-up for larger volume trades"
    }

    with open(history_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(deposit_record) + "\n")

    print(f">>> [Capital] Added ₹{amount:,.2f} | Current: ₹{new_current:,.2f} | Starting: ₹{new_starting:,.2f}")
    return deposit_record

def get_capital_status() -> dict:
    """Returns current capital levels, slot capacities, and trade allocation limits."""
    from hermes_trading.config import get_state_dir
    state_path = get_state_dir()
    goal_path = state_path / "goal.yaml"
    strategy_path = state_path / "strategy.yaml"

    goal = yaml.safe_load(goal_path.read_text()) if goal_path.exists() else {}
    strategy = yaml.safe_load(strategy_path.read_text()) if strategy_path.exists() else {}

    current_capital = float(goal.get("current_capital_inr", 50000))
    starting_capital = float(goal.get("starting_capital_inr", 50000))
    max_active = int(strategy.get("max_active_positions", 4))
    position_size_r = float(strategy.get("position_size_r", 0.9))

    slot_capital = current_capital / max_active if max_active > 0 else current_capital
    trade_allocation = slot_capital * position_size_r

    return {
        "current_capital_inr": current_capital,
        "starting_capital_inr": starting_capital,
        "max_active_positions": max_active,
        "position_size_r": position_size_r,
        "slot_capital_inr": round(slot_capital, 2),
        "trade_allocation_per_slot_inr": round(trade_allocation, 2)
    }

def get_capital_history() -> list[dict]:
    """Retrieves deposit and capital history records."""
    from hermes_trading.config import get_state_dir
    history_path = get_state_dir() / "capital_history.jsonl"
    if not history_path.exists():
        return []
    records = []
    with open(history_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    records.append(json.loads(line))
                except Exception:
                    continue
    return records

def main():
    parser = argparse.ArgumentParser(description="Manage Hermes Trading Agent Portfolio Capital")
    parser.add_argument("--add", type=float, help="Amount in INR to add to portfolio capital")
    parser.add_argument("--no-base-update", action="store_true", help="Do not update starting_capital_inr base")
    parser.add_argument("--note", type=str, default="", help="Note or reason for deposit")
    parser.add_argument("--status", action="store_true", help="Show current capital allocation status")
    parser.add_argument("--history", action="store_true", help="Show deposit history")

    args = parser.parse_args()

    if args.add:
        update_base = not args.no_base_update
        res = add_funds(args.add, update_starting_capital=update_base, note=args.note)
        print(f"Successfully added ₹{args.add:,.2f} to portfolio capital.")
        print(f"New Realized Capital: ₹{res['new_current_capital']:,.2f}")
        print(f"New Starting Capital Base: ₹{res['new_starting_capital']:,.2f}")
    elif args.status:
        st = get_capital_status()
        print("\n--- Portfolio Capital & Trade Capacity Status ---")
        print(f"Available Realized Capital: ₹{st['current_capital_inr']:,.2f}")
        print(f"Starting / Base Capital:   ₹{st['starting_capital_inr']:,.2f}")
        print(f"Max Concurrent Slots:      {st['max_active_positions']}")
        print(f"Risk per Slot (position_r): {st['position_size_r']*100:.0f}%")
        print(f"Capital per Slot:          ₹{st['slot_capital_inr']:,.2f}")
        print(f"Max Volume / Trade Size:   ₹{st['trade_allocation_per_slot_inr']:,.2f}")
    elif args.history:
        history = get_capital_history()
        print(f"\n--- Capital History ({len(history)} entries) ---")
        for h in history:
            print(f"[{h.get('timestamp')}] Added ₹{h.get('amount', 0):,.2f} | Realized: ₹{h.get('new_current_capital', 0):,.2f} | Note: {h.get('note', '')}")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()

