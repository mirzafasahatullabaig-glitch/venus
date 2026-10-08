"""Distils one bot's turns in a finished conversation into a single-sentence
memory, for memory_store to persist.

Reuses the one Ollama adapter (services.ollama_client); it adds no new way to
reach a model. If the model call fails or is disabled, it falls back to a trimmed
snippet of the bot's last turn, so a run always produces *some* memory rather
than silently storing nothing.
"""
from __future__ import annotations

from services.ollama_client import stream_chat

_SYSTEM = (
    "You summarise, in ONE short sentence and in the first person, what a bot "
    "concluded or learned in a conversation with another bot. No preamble, no "
    "quotes — just the sentence."
)


def snippet_of(turns: list[dict], bot: str, limit: int = 160) -> str:
    """A memory straight from the bot's last turn, trimmed. '' if it never spoke.

    Used both as the fallback when a summary call fails and as the whole memory
    when config has memory.summarize = false (no extra model call)."""
    mine = [t for t in turns if t.get("bot") == bot]
    if not mine:
        return ""
    text = " ".join((mine[-1].get("text") or "").split())
    return text[: limit - 3] + "..." if len(text) > limit else text


async def summarise_bot(
    *,
    turns: list[dict],
    bot: str,
    task: str,
    ollama_url: str,
    model: str,
    num_ctx: int,
) -> str:
    """One-sentence, first-person memory for `bot`. Falls back to a snippet on
    any error. Returns '' only when the bot took no turn."""
    mine = [t for t in turns if t.get("bot") == bot]
    if not mine:
        return ""
    transcript = "\n".join(
        f"{'you' if t.get('bot') == bot else 'the other bot'}: {t.get('text', '')}"
        for t in turns
    )
    user = f"TASK:\n{task}\n\nTRANSCRIPT:\n{transcript}\n\nYour one-sentence takeaway:"
    try:
        parts: list[str] = []
        async for piece in stream_chat(
            ollama_url=ollama_url,
            model=model,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user}],
            num_ctx=num_ctx,
        ):
            parts.append(piece)
        out = " ".join("".join(parts).split()).strip().strip('"')
        return out or snippet_of(turns, bot)
    except Exception:
        return snippet_of(turns, bot)
