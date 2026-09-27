"""Loads config.toml (and later experiment TOMLs). NOTHING else reads config files.

The rest of the app imports `get_config()` and reads fields off the returned
object — no other module opens config.toml or knows where it lives.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

try:  # Python 3.11+ has tomllib in the stdlib
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover - py<3.11 fallback
    import tomli as _toml  # type: ignore[no-redef]

# brain/app/config.py -> brain/ is two levels up (the source tree).
BRAIN_DIR = Path(__file__).resolve().parent.parent

# When frozen by PyInstaller (--onefile), bundled assets (web/, personas/) are
# extracted to sys._MEIPASS, and config.toml lives beside the .exe so the user
# can edit it. In source runs, both are just the brain/ tree.
_FROZEN = getattr(sys, "frozen", False)
ASSET_DIR = Path(getattr(sys, "_MEIPASS", BRAIN_DIR)) if _FROZEN else BRAIN_DIR
CONFIG_PATH = (Path(sys.executable).parent / "config.toml") if _FROZEN else (BRAIN_DIR / "config.toml")


@dataclass(frozen=True)
class BotConfig:
    model: str
    body: str
    persona_path: str  # relative to BRAIN_DIR, e.g. "personas/bot1_esp32.txt"

    def read_persona(self) -> str:
        return (ASSET_DIR / self.persona_path).read_text(encoding="utf-8")


@dataclass(frozen=True)
class Config:
    api_key: str
    port: int
    ollama_url: str
    num_ctx: int
    bots: dict[str, BotConfig]


@dataclass(frozen=True)
class Experiment:
    """One reproducible experiment: the task, the turn budget, the stop marker,
    and the bot line-up (models + personas)."""

    task: str
    turn_limit: int
    stop_marker: str | None
    bots: dict[str, BotConfig]


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Load config.toml once and cache it. Raises a clear error if missing."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"{CONFIG_PATH} not found. Copy config.example.toml to config.toml "
            "and set a real api_key."
        )

    with CONFIG_PATH.open("rb") as f:
        raw = _toml.load(f)

    return Config(
        api_key=raw["api_key"],
        port=int(raw.get("port", 8080)),
        ollama_url=raw.get("ollama_url", "http://127.0.0.1:11434"),
        num_ctx=int(raw.get("num_ctx", 4096)),
        bots=_bots_from(raw),
    )


def _bots_from(raw: dict) -> dict[str, BotConfig]:
    return {
        name: BotConfig(
            model=spec["model"], body=spec["body"], persona_path=spec["persona"]
        )
        for name, spec in raw.get("bots", {}).items()
    }


def load_experiment(path: str | Path) -> Experiment:
    """Load an experiment TOML. Paths inside it are relative to BRAIN_DIR."""
    p = Path(path)
    if not p.is_absolute():
        p = BRAIN_DIR / p
    if not p.exists():
        raise FileNotFoundError(f"Experiment file not found: {p}")

    with p.open("rb") as f:
        raw = _toml.load(f)

    return Experiment(
        task=raw["task"],
        turn_limit=int(raw.get("turn_limit", 6)),
        stop_marker=raw.get("stop_marker"),
        bots=_bots_from(raw),
    )
