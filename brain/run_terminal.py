"""Phase 2 runner: two bots hold a conversation in the terminal.

This is glue — it wires core.conversation (pure logic) to the ollama_client
(the only Ollama adapter) and prints the exchange live. Run from brain/:

    python run_terminal.py "Design a cheap way to know if my plant needs water."
    python run_terminal.py --turns 8 "your task here"
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from app.config import get_config
from core.bot import Bot
from core.conversation import run_conversation
from services.ollama_client import stream_chat

# ANSI colours so the two voices are easy to tell apart in the terminal.
C1, C2, DIM, RESET = "\033[36m", "\033[35m", "\033[2m", "\033[0m"


def build_bots() -> list[Bot]:
    cfg = get_config()
    bots: list[Bot] = []
    for name in ("bot1", "bot2"):
        if name not in cfg.bots:
            continue
        spec = cfg.bots[name]
        bots.append(
            Bot(name=name, persona=spec.read_persona(), model=spec.model, body=spec.body)
        )
    if len(bots) < 2:
        raise SystemExit("Need bot1 and bot2 configured in config.toml.")
    return bots


def make_turn_fn(colour_of: dict[str, str]):
    """Return a sync turn_fn that streams a reply from Ollama and prints it live."""
    cfg = get_config()

    def turn_fn(bot: Bot, messages: list[dict[str, str]]) -> str:
        colour = colour_of.get(bot.name, "")
        print(f"\n{colour}[{bot.name} · {bot.body} · {bot.model}]{RESET}")

        async def collect() -> str:
            parts: list[str] = []
            async for piece in stream_chat(
                ollama_url=cfg.ollama_url,
                model=bot.model,
                system=bot.persona,
                messages=messages,
                num_ctx=cfg.num_ctx,
            ):
                parts.append(piece)
                print(f"{colour}{piece}{RESET}", end="", flush=True)
            print()
            return "".join(parts)

        return asyncio.run(collect())

    return turn_fn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a two-bot conversation.")
    parser.add_argument("task", nargs="?", default="Introduce yourselves and agree on one small task you could do together.")
    parser.add_argument("--turns", type=int, default=6, help="total turns (default 6)")
    args = parser.parse_args()

    bots = build_bots()
    colour_of = {bots[0].name: C1, bots[1].name: C2}

    print(f"{DIM}TASK: {args.task}{RESET}")
    run_conversation(
        task=args.task,
        bots=bots,
        turn_fn=make_turn_fn(colour_of),
        max_turns=args.turns,
    )
    print(f"\n{DIM}--- done ({args.turns} turns) ---{RESET}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
