from pathlib import Path

def get_state_dir() -> Path:
    # If on Railway with persistent volume mounted at /data
    vol_path = Path("/data")
    if vol_path.exists():
        vol_path.mkdir(exist_ok=True)
        # Check if we need to copy template configs
        template_dir = Path("state")
        for template in ["goal.yaml", "strategy.yaml"]:
            dest = vol_path / template
            src = template_dir / template
            if src.exists() and not dest.exists():
                try:
                    dest.write_text(src.read_text())
                except Exception as e:
                    print(f"Error copying template {template} to /data: {e}")
        # Ensure history directory exists
        (vol_path / "history").mkdir(exist_ok=True)
        return vol_path
    else:
        local_path = Path("state")
        local_path.mkdir(exist_ok=True)
        (local_path / "history").mkdir(exist_ok=True)
        return local_path
