"""The ONLY file that writes to runs/. Turns a conversation into a saved,
reproducible JSON record.

Nothing else in the app opens runs/ for writing; analysis/ reads these files but
never imports this module.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# brain/services/run_logger.py -> repo root is three levels up; runs/ sits there.
RUNS_DIR = Path(__file__).resolve().parent.parent.parent / "runs"


@dataclass
class RunLogger:
    """Accumulate per-turn records, then write one runs/<timestamp>.json file."""

    task: str
    turn_limit: int
    stop_marker: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    turns: list[dict] = field(default_factory=list)

    def add_turn(
        self,
        *,
        bot: str,
        model: str,
        persona: str,
        text: str,
        latency_s: float,
        tokens: int | None,
    ) -> None:
        self.turns.append(
            {
                "index": len(self.turns),
                "bot": bot,
                "model": model,
                "persona": persona,
                "text": text,
                "latency_s": round(latency_s, 3),
                "tokens": tokens,
            }
        )

    def save(self, *, converged: bool) -> Path:
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = self.started_at.strftime("%Y%m%dT%H%M%SZ")
        path = RUNS_DIR / f"{stamp}.json"
        record = {
            "started_at": self.started_at.isoformat(),
            "task": self.task,
            "turn_limit": self.turn_limit,
            "stop_marker": self.stop_marker,
            "converged": converged,
            "turns": self.turns,
        }
        path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        return path


def list_runs() -> list[dict]:
    """Summaries of saved runs, newest first: {name, task, turns, converged}."""
    if not RUNS_DIR.exists():
        return []
    out: list[dict] = []
    for p in sorted(RUNS_DIR.glob("*.json"), reverse=True):
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        out.append(
            {
                "name": p.stem,
                "task": rec.get("task", ""),
                "turns": len(rec.get("turns", [])),
                "converged": rec.get("converged", False),
                "started_at": rec.get("started_at"),
            }
        )
    return out


def read_run(name: str) -> dict:
    """Read one run by its stem (no path traversal). Raises if missing/invalid."""
    safe = Path(name).name  # strip any directory components
    path = RUNS_DIR / f"{safe}.json"
    if not path.exists():
        raise FileNotFoundError(f"No such run: {safe}")
    return json.loads(path.read_text(encoding="utf-8"))


def append_judge(name: str, judgment: dict) -> Path:
    """Attach a judge verdict to a saved run file under the "judge" key."""
    safe = Path(name).name
    path = RUNS_DIR / f"{safe}.json"
    if not path.exists():
        raise FileNotFoundError(f"No such run: {safe}")
    rec = json.loads(path.read_text(encoding="utf-8"))
    rec["judge"] = judgment
    path.write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
