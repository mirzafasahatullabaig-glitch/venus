"""The ONLY file that writes to memory/. Gives each bot a cross-run memory so a
new conversation can recall what the bot concluded in earlier ones.

Mirrors run_logger's discipline: nothing else opens memory/ for writing, and the
format is plain inspectable JSON (one file per bot). The summaries themselves are
produced by the caller (see services.summarizer); this module only stores and
recalls them.

    memory/
      bot1.json   {"bot": "bot1", "entries": [{ts, run, task, summary}, ...]}
      bot2.json
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

# brain/services/memory_store.py -> repo root is three levels up; memory/ sits
# there, beside runs/ (same "data, not code" bucket).
MEMORY_DIR = Path(__file__).resolve().parent.parent.parent / "memory"


def _path_for(bot: str) -> Path:
    safe = Path(bot).name  # strip any directory components; no traversal
    return MEMORY_DIR / f"{safe}.json"


def _load(bot: str) -> dict:
    path = _path_for(bot)
    if not path.exists():
        return {"bot": bot, "entries": []}
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # A corrupt or unreadable memory file must never break a run; start fresh.
        return {"bot": bot, "entries": []}
    rec.setdefault("bot", bot)
    rec.setdefault("entries", [])
    return rec


def remember(bot: str, *, run: str, task: str, summary: str) -> None:
    """Append one memory entry for `bot`. `run` is the saved run's stem."""
    summary = (summary or "").strip()
    if not summary:
        return
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    rec = _load(bot)
    rec["entries"].append(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "run": run,
            "task": task,
            "summary": summary,
        }
    )
    _path_for(bot).write_text(
        json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def recall(bot: str, *, limit: int = 3) -> str:
    """The N most recent summaries for `bot`, as a recall block to append to its
    system prompt. Returns "" when the bot has no memory (so callers can append
    unconditionally without changing the prompt for a fresh bot)."""
    if limit <= 0:
        return ""
    entries = _load(bot)["entries"][-limit:]
    if not entries:
        return ""
    lines = ["[Memory — things you recall from earlier conversations]"]
    for e in entries:
        date = (e.get("ts") or "")[:10]  # YYYY-MM-DD
        task = (e.get("task") or "").strip().replace("\n", " ")
        if len(task) > 60:
            task = task[:57] + "..."
        stamp = f"({date}) " if date else ""
        prefix = f'{stamp}On "{task}": ' if task else stamp
        lines.append(f"- {prefix}{e['summary']}")
    return "\n".join(lines)
