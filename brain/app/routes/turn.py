"""POST /turn — one persona-shaped model turn, streamed back as plain text.

This route only wires the request to the services; it holds no conversation
logic (that lives in core/, from Phase 2 on).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import get_config
from app.security import require_api_key
from services.ollama_client import stream_chat

router = APIRouter()


class Message(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class TurnRequest(BaseModel):
    persona: str = Field(..., description="System prompt shaping this turn.")
    transcript: list[Message] = Field(
        default_factory=list, description="Conversation so far."
    )
    model: str | None = Field(
        default=None, description="Model id; falls back to bots.bot1 in config."
    )


def _default_model() -> str:
    bots = get_config().bots
    if "bot1" in bots:
        return bots["bot1"].model
    if bots:
        return next(iter(bots.values())).model
    raise ValueError("No model given and no bots configured in config.toml.")


@router.post("/turn", dependencies=[Depends(require_api_key)])
async def turn(req: TurnRequest) -> StreamingResponse:
    cfg = get_config()
    model = req.model or _default_model()
    messages = [m.model_dump() for m in req.transcript]

    async def body():
        async for piece in stream_chat(
            ollama_url=cfg.ollama_url,
            model=model,
            system=req.persona,
            messages=messages,
            num_ctx=cfg.num_ctx,
        ):
            yield piece

    return StreamingResponse(body(), media_type="text/plain; charset=utf-8")
