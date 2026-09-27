"""A tiny in-process fan-out hub so device bodies can WATCH a live run.

The cockpit or a device starts a run via POST /run; each event is published here,
and every GET /watch subscriber (the Pi relay, other viewers) receives it. This
is in-memory infrastructure, not business logic — the turn-taking still lives in
core/.
"""
from __future__ import annotations

import asyncio


class EventHub:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def publish(self, event: dict) -> None:
        for q in list(self._subscribers):
            q.put_nowait(event)


# One process-wide hub.
hub = EventHub()
