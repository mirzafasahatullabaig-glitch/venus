"""The ONLY file that talks to Ollama. Nothing else imports httpx or knows the
Ollama wire format.

Exposes one thing: `stream_chat(...)`, an async generator that yields the reply
text chunk by chunk. Keep-alive is set so a loaded model stays resident between
turns (no per-turn cold reload).
"""
from __future__ import annotations

import json
from typing import AsyncIterator, Callable, Optional

import httpx

# -1 = keep the model resident indefinitely (matches OLLAMA_KEEP_ALIVE=-1).
KEEP_ALIVE = -1


async def stream_chat(
    *,
    ollama_url: str,
    model: str,
    system: str,
    messages: list[dict[str, str]],
    num_ctx: int,
    keep_alive: int = KEEP_ALIVE,
    timeout: float = 300.0,
    on_stats: Optional[Callable[[dict], None]] = None,
) -> AsyncIterator[str]:
    """Stream one chat completion from Ollama's /api/chat.

    `messages` is the transcript so far as [{"role": ..., "content": ...}, ...].
    The persona is prepended as a system message. Yields text fragments as they
    arrive; raises httpx.HTTPStatusError on a non-2xx response.

    If `on_stats` is given, it's called once with the final "done" chunk, which
    carries Ollama's counters (eval_count, prompt_eval_count, total_duration, ...).
    """
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, *messages],
        "stream": True,
        "keep_alive": keep_alive,
        "options": {"num_ctx": num_ctx},
    }

    url = ollama_url.rstrip("/") + "/api/chat"
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", url, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                chunk = json.loads(line)
                if "error" in chunk:
                    raise RuntimeError(f"Ollama error: {chunk['error']}")
                piece = chunk.get("message", {}).get("content", "")
                if piece:
                    yield piece
                if chunk.get("done"):
                    if on_stats is not None:
                        on_stats(chunk)
                    break
