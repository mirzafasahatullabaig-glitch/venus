"""POST /run  — stream a full two-bot conversation to the cockpit as SSE.
GET  /runs  — list past runs.        GET /runs/{name} — fetch one run.

This route wires services + core; the turn-taking lives in core.conversation and
the Ollama call in services.ollama_client.
"""
from __future__ import annotations

import json
import time
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import get_config
from app.hub import hub
from app.security import require_api_key
from core.bot import Bot
from core.conversation import stream_conversation
from services.ollama_client import stream_chat
from services import memory_store, run_logger
from services.summarizer import snippet_of, summarise_bot

router = APIRouter(dependencies=[Depends(require_api_key)])


class RunRequest(BaseModel):
    task: str
    turn_limit: int = Field(default=8, ge=1, le=50)
    stop_marker: str | None = "CONVERGED"
    # Optional per-bot persona overrides (empty/None => use the configured file).
    personas: dict[str, str] = Field(default_factory=dict)


def _build_bots(req: RunRequest) -> list[Bot]:
    cfg = get_config()
    bots: list[Bot] = []
    for name in ("bot1", "bot2"):
        if name not in cfg.bots:
            continue
        spec = cfg.bots[name]
        override = req.personas.get(name)
        persona = override.strip() if override and override.strip() else spec.read_persona()
        bots.append(Bot(name=name, persona=persona, model=spec.model, body=spec.body))
    if len(bots) < 2:
        raise HTTPException(status_code=400, detail="bot1 and bot2 must be configured.")
    return bots


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/run")
async def run(req: RunRequest) -> StreamingResponse:
    cfg = get_config()
    bots = _build_bots(req)
    logger = run_logger.RunLogger(
        task=req.task, turn_limit=req.turn_limit, stop_marker=req.stop_marker
    )

    # Read seam: each bot's system prompt is its persona plus a recall block of
    # what it concluded in earlier runs. recall() returns "" for a bot with no
    # memory (or when memory is disabled), so a fresh bot's prompt is unchanged.
    mem = cfg.memory
    recalled = {
        b.name: (memory_store.recall(b.name, limit=mem.recall_limit) if mem.enabled else "")
        for b in bots
    }
    recalled_count = sum(1 for v in recalled.values() if v)

    def system_for(bot: Bot) -> str:
        block = recalled.get(bot.name, "")
        return f"{bot.persona}\n\n{block}" if block else bot.persona

    # Per-turn scratch, filled by token_stream and read on turn_end for logging.
    current = {"t0": 0.0, "stats": {}}

    def token_stream(bot: Bot, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        current["t0"] = time.perf_counter()
        current["stats"] = {}
        return stream_chat(
            ollama_url=cfg.ollama_url,
            model=bot.model,
            system=system_for(bot),
            messages=messages,
            num_ctx=cfg.num_ctx,
            on_stats=current["stats"].update,
        )

    async def events() -> AsyncIterator[str]:
        bot_by_name = {b.name: b for b in bots}
        converged = False
        if recalled_count:
            rec_ev = {"type": "recalled", "count": recalled_count,
                      "limit": mem.recall_limit}
            hub.publish(rec_ev)
            yield _sse(rec_ev)
        try:
            async for ev in stream_conversation(
                task=req.task,
                bots=bots,
                token_stream=token_stream,
                max_turns=req.turn_limit,
                stop_marker=req.stop_marker,
            ):
                if ev["type"] == "turn_end":
                    bot = bot_by_name[ev["bot"]]
                    latency = time.perf_counter() - current["t0"]
                    ev = {**ev, "latency_s": round(latency, 3),
                          "tokens": current["stats"].get("eval_count"),
                          "model": bot.model}
                    logger.add_turn(
                        bot=bot.name, model=bot.model, persona=bot.persona,
                        text=ev["text"], latency_s=latency,
                        tokens=current["stats"].get("eval_count"),
                    )
                elif ev["type"] == "done":
                    converged = ev["converged"]
                hub.publish(ev)          # fan out to watching bodies
                yield _sse(ev)
        except Exception as exc:  # surface Ollama/other errors to the page
            err = {"type": "error", "message": str(exc)}
            hub.publish(err)
            yield _sse(err)
            return
        path = logger.save(converged=converged)
        saved = {"type": "saved", "name": path.stem}
        hub.publish(saved)
        yield _sse(saved)

        # Write seam: distil this run into a one-sentence memory per bot so the
        # next run can recall it. Never let memory failure break a completed run.
        if mem.enabled:
            try:
                stored = 0
                for bot in bots:
                    if mem.summarize:
                        summary = await summarise_bot(
                            turns=logger.turns, bot=bot.name, task=req.task,
                            ollama_url=cfg.ollama_url, model=bot.model,
                            num_ctx=cfg.num_ctx,
                        )
                    else:
                        summary = snippet_of(logger.turns, bot.name)
                    if summary:
                        memory_store.remember(
                            bot.name, run=path.stem, task=req.task, summary=summary
                        )
                        stored += 1
                remembered = {"type": "remembered", "count": stored}
                hub.publish(remembered)
                yield _sse(remembered)
            except Exception as exc:  # memory is best-effort, never fatal
                yield _sse({"type": "memory_error", "message": str(exc)})

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/runs")
async def runs() -> list[dict]:
    return run_logger.list_runs()


@router.get("/runs/{name}")
async def one_run(name: str) -> dict:
    try:
        return run_logger.read_run(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Run not found.")
