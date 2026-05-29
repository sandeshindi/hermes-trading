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
    
    # 2. Check for backup templates in our safe build-time templates folder
    template_dir = Path("/app/state_templates")
    if not template_dir.exists():
        template_dir = Path("state_templates")
        
    if template_dir.exists():
        for template in ["goal.yaml", "strategy.yaml"]:
            dest = active_dir / template
            src = template_dir / template
            # Restore template if missing in active_dir
            if src.exists() and not dest.exists():
                try:
                    dest.write_text(src.read_text())
                    print(f"Successfully initialized {template} in {active_dir}")
                except Exception as e:
                    print(f"Error copying template {template} to {active_dir}: {e}")
                    
    return active_dir
