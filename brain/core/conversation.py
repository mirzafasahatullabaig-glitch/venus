"""The turn-taking loop + stop conditions. PURE LOGIC.

It never calls Ollama itself. The caller passes a `turn_fn(bot, messages) -> str`
that produces one reply; here we only decide who speaks, in what order, on what
context, and when to stop. That makes this loop unit-testable with a fake turn
function (no models, no network).
"""
from __future__ import annotations

from typing import AsyncIterator, Callable, Optional

from core.bot import Bot
from core.transcript import Transcript

# A function that, given a bot and the messages it should see, returns its reply.
TurnFn = Callable[[Bot, list[dict[str, str]]], str]
# Optional hook fired after each completed turn (e.g. to print/stream it live).
OnTurn = Callable[[int, Bot, str], None]
# An async token producer: given a bot and its messages, yields reply fragments.
TokenStream = Callable[[Bot, list[dict[str, str]]], AsyncIterator[str]]


def run_conversation(
    *,
    task: str,
    bots: list[Bot],
    turn_fn: TurnFn,
    max_turns: int,
    on_turn: Optional[OnTurn] = None,
    transcript: Optional[Transcript] = None,
    stop_marker: Optional[str] = None,
) -> Transcript:
    """Alternate the bots for up to `max_turns`, appending each reply.

    Bots speak round-robin in list order (bot[0], bot[1], bot[0], ...). Stops at
    the turn limit, or early if `stop_marker` appears in a reply (the bots
    signalling they've converged). Returns the filled transcript, with
    `transcript.converged` set when an early stop fired.
    """
    if not bots:
        raise ValueError("run_conversation needs at least one bot.")

    transcript = transcript or Transcript(task=task)

    for i in range(max_turns):
        speaker = bots[i % len(bots)]
        messages = transcript.render_for(speaker.name)
        reply = turn_fn(speaker, messages)
        transcript.append(speaker.name, reply)
        if on_turn is not None:
            on_turn(i, speaker, reply)
        if stop_marker and stop_marker in reply:
            transcript.converged = True
            break

    return transcript


async def stream_conversation(
    *,
    task: str,
    bots: list[Bot],
    token_stream: TokenStream,
    max_turns: int,
    transcript: Optional[Transcript] = None,
    stop_marker: Optional[str] = None,
) -> AsyncIterator[dict]:
    """Same turn-taking as run_conversation, but streaming.

    Drives an async `token_stream` and yields structured events as they happen:
      {"type": "turn_start", index, bot, model, body}
      {"type": "token",      index, bot, text}
      {"type": "turn_end",   index, bot, text}
      {"type": "done",       converged, turns}

    Pure logic: it decides order/context/stop; it never talks to Ollama or HTTP.
    """
    if not bots:
        raise ValueError("stream_conversation needs at least one bot.")

    transcript = transcript or Transcript(task=task)

    for i in range(max_turns):
        speaker = bots[i % len(bots)]
        messages = transcript.render_for(speaker.name)
        yield {
            "type": "turn_start",
            "index": i,
            "bot": speaker.name,
            "model": speaker.model,
            "body": speaker.body,
        }

        parts: list[str] = []
        async for piece in token_stream(speaker, messages):
            parts.append(piece)
            yield {"type": "token", "index": i, "bot": speaker.name, "text": piece}

        text = "".join(parts)
        transcript.append(speaker.name, text)
        yield {"type": "turn_end", "index": i, "bot": speaker.name, "text": text}

        if stop_marker and stop_marker in text:
            transcript.converged = True
            break

    yield {"type": "done", "converged": transcript.converged, "turns": len(transcript.turns)}
