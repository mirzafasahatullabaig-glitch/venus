"""GET /watch — subscribe to the live run event stream (SSE).

Device bodies (the Pi relay) and extra viewers connect here to watch whatever run
is in progress, whoever started it.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.hub import hub
from app.security import require_api_key

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/watch")
async def watch() -> StreamingResponse:
    q = hub.subscribe()

    async def gen():
        # An initial comment lets clients confirm the stream is open.
        yield ": connected\n\n"
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"  # keep proxies/tailnet from idling out
        finally:
            hub.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream")
