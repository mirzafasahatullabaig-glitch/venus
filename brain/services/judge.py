"""An optional judge pass over a finished conversation.

Two layers:
  * a DETERMINISTIC verdict computed from the transcript alone (converged? who
    declared it? who led by word share?) — always available, no model needed;
  * an OPTIONAL model verdict — if an Ollama url + judge model are supplied, a
    neutral judge model is asked for {converged, leader, why}. It composes
    services.ollama_client (still the only file that talks to Ollama) and fails
    soft: if the model is unreachable, only the deterministic part is returned.

The result is meant to be appended to the run file (via run_logger.append_judge).
"""
from __future__ import annotations

import asyncio
import json
import re

from services.ollama_client import stream_chat

_WORD = re.compile(r"[a-z0-9]+")
_JSON = re.compile(r"\{.*\}", re.DOTALL)


def _word_counts(turns: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for t in turns:
        counts[t["bot"]] = counts.get(t["bot"], 0) + len(_WORD.findall(t["text"].lower()))
    return counts


def _deterministic(turns: list[dict], converged: bool, stop_marker: str | None) -> dict:
    declared_by = None
    if stop_marker:
        for t in turns:
            if stop_marker in t["text"]:
                declared_by = t["bot"]
                break

    counts = _word_counts(turns)
    total = sum(counts.values()) or 1
    word_share = {b: round(c / total, 2) for b, c in counts.items()}

    if converged and declared_by:
        leader = declared_by
    elif counts:
        top = max(counts, key=counts.get)
        others = [c for b, c in counts.items() if b != top]
        leader = top if not others or counts[top] > max(others) else "neither"
    else:
        leader = "neither"

    return {
        "converged": converged,
        "declared_by": declared_by,
        "word_share": word_share,
        "leader_heuristic": leader,
    }


async def _model_verdict(turns, task, ollama_url, model, num_ctx) -> dict:
    transcript = "\n".join(f"{t['bot']}: {t['text']}" for t in turns)
    system = (
        "You are a neutral judge of a conversation between two bots, bot1 and "
        "bot2, working on a task. Read the transcript and reply with ONLY compact "
        'JSON: {"converged": true or false, "leader": "bot1" or "bot2" or '
        '"neither", "why": "one short sentence"}.'
    )
    user = f"TASK:\n{task}\n\nTRANSCRIPT:\n{transcript}"
    parts: list[str] = []
    async for piece in stream_chat(
        ollama_url=ollama_url, model=model, system=system,
        messages=[{"role": "user", "content": user}], num_ctx=num_ctx,
    ):
        parts.append(piece)
    raw = "".join(parts).strip()
    m = _JSON.search(raw)
    if m:
        try:
            return {"model": model, "verdict": json.loads(m.group(0))}
        except json.JSONDecodeError:
            pass
    return {"model": model, "verdict_raw": raw}


def judge_run(
    *,
    turns: list[dict],
    task: str,
    converged: bool,
    stop_marker: str | None = None,
    ollama_url: str | None = None,
    model: str | None = None,
    num_ctx: int = 4096,
) -> dict:
    """Return a judgment dict. Deterministic always; model verdict when possible."""
    result = _deterministic(turns, converged, stop_marker)
    if ollama_url and model:
        try:
            result["model_judge"] = asyncio.run(
                _model_verdict(turns, task, ollama_url, model, num_ctx)
            )
        except Exception as exc:
            result["model_judge"] = {"model": model, "error": str(exc)}
    return result
