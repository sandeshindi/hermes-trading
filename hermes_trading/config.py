from pathlib import Path

def get_state_dir() -> Path:
    # 1. Resolve the active state directory (Production Volume /data or Local state/)
    vol_path = Path("/data")
    if vol_path.exists():
        active_dir = vol_path
    else:
        active_dir = Path("state")
        
    active_dir.mkdir(exist_ok=True)
    (active_dir / "history").mkdir(exist_ok=True)
    
    # Check for force reset env var to wipe history
    import os
    if os.getenv("RESET_TRADING_HISTORY") == "true":
        for file_to_del in ["trades.jsonl", "hypotheses.jsonl", "prices.json", "heartbeat.json"]:
            fp = active_dir / file_to_del
            if fp.exists():
                try:
                    fp.unlink()
                    print(f"RESET_TRADING_HISTORY is active. Deleted {file_to_del} in volume.")
                except Exception as e:
                    print(f"Error deleting {file_to_del}: {e}")
                    
        # Reset goal capital
        goal_path = active_dir / "goal.yaml"
        if goal_path.exists():
            try:
                import yaml
                goal_data = yaml.safe_load(goal_path.read_text())
                if isinstance(goal_data, dict):
                    start_cap = goal_data.get("starting_capital_inr", 50000)
                    goal_data["current_capital_inr"] = start_cap
                    goal_path.write_text(yaml.safe_dump(goal_data, sort_keys=False))
                    print(f"RESET_TRADING_HISTORY is active. Reset current_capital_inr to {start_cap} in goal.yaml")
            except Exception as e:
                print(f"Error resetting goal capital: {e}")
    
    # 2. Check for backup templates in our safe build-time templates folder
    template_dir = Path("/app/state_templates")
    if not template_dir.exists():
        template_dir = Path("state_templates")
        
    if template_dir.exists():
        for template in ["goal.yaml", "strategy.yaml"]:
            dest = active_dir / template
            src = template_dir / template
            # Restore template if missing in active_dir
            if src.exists():
                import os
                if os.getenv("FORCE_OVERWRITE_STRATEGY") == "true":
                    try:
                        dest.write_text(src.read_text())
                        print(f"FORCE_OVERWRITE_STRATEGY is active. Overwrote {template} in volume with git template.")
                    except Exception as e:
                        print(f"Error force overwriting {template}: {e}")
                    continue

                if not dest.exists():
                    try:
                        dest.write_text(src.read_text())
                        print(f"Successfully initialized {template} in {active_dir}")
                    except Exception as e:
                        print(f"Error copying template {template} to {active_dir}: {e}")
                elif template == "strategy.yaml":
                    # Automatically migrate missing keys from the template to the active volume strategy
                    try:
                        import yaml
                        src_yaml = yaml.safe_load(src.read_text())
                        dest_yaml = yaml.safe_load(dest.read_text())
                        migrated = False
                        if isinstance(src_yaml, dict) and isinstance(dest_yaml, dict):
                            for k, v in src_yaml.items():
                                if k not in dest_yaml:
                                    dest_yaml[k] = v
                                    migrated = True
                            if migrated:
                                dest.write_text(yaml.safe_dump(dest_yaml, sort_keys=False))
                                print(f"Successfully migrated new default keys to active strategy.yaml in volume")
                    except Exception as e:
                        print(f"Error migrating strategy template: {e}")
                    
    return active_dir
