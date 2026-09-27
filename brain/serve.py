"""Entry point for the packaged brain (venus.exe) and for `python serve.py`.

Starts uvicorn serving the cockpit + API. When frozen and no config.toml sits
beside the exe, it writes a template there and asks the user to fill it in,
instead of crashing to a closing console window.
"""
from __future__ import annotations

import shutil
import sys

from app.config import ASSET_DIR, CONFIG_PATH, _FROZEN


def _pause_if_frozen() -> None:
    if _FROZEN:
        try:
            input("\nPress Enter to close...")
        except EOFError:
            pass


def main() -> int:
    if not CONFIG_PATH.exists():
        template = ASSET_DIR / "config.example.toml"
        if _FROZEN and template.exists():
            shutil.copyfile(template, CONFIG_PATH)
            print(f"Created {CONFIG_PATH}")
            print("Edit it - set a real api_key - then launch venus again.")
        else:
            print(f"Missing config: {CONFIG_PATH}")
            print("Copy config.example.toml to config.toml and set api_key.")
        _pause_if_frozen()
        return 1

    # Import after the config check so a missing config gives a clean message.
    import uvicorn

    from app.config import get_config
    from app.main import app

    cfg = get_config()
    shown = "127.0.0.1" if cfg.host in ("0.0.0.0", "") else cfg.host
    print(f"Venus cockpit -> http://{shown}:{cfg.port}")
    if cfg.host not in ("127.0.0.1", "localhost"):
        print(f"(listening on {cfg.host}:{cfg.port} - reachable over the tailnet)")
    uvicorn.run(app, host=cfg.host or "127.0.0.1", port=cfg.port, log_level="info")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
