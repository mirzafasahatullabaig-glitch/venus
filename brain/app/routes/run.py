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
from services import run_logger

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

    # Per-turn scratch, filled by token_stream and read on turn_end for logging.
    current = {"t0": 0.0, "stats": {}}

    def token_stream(bot: Bot, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        current["t0"] = time.perf_counter()
        current["stats"] = {}
        return stream_chat(
            ollama_url=cfg.ollama_url,
            model=bot.model,
            system=bot.persona,
            messages=messages,
            num_ctx=cfg.num_ctx,
            on_stats=current["stats"].update,
        )

    async def events() -> AsyncIterator[str]:
        bot_by_name = {b.name: b for b in bots}
        converged = False
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
