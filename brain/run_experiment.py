"""Phase 3 runner: run an experiment TOML and save a reproducible transcript.

Glue only. Wires config.load_experiment + core.conversation (pure) +
ollama_client (the Ollama adapter) + run_logger (the runs/ writer). Run from brain/:

    python run_experiment.py experiments/example.toml
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time

from app.config import get_config, load_experiment
from core.bot import Bot
from core.conversation import run_conversation
from services import judge as judge_service
from services import run_logger
from services.ollama_client import stream_chat
from services.run_logger import RunLogger

C1, C2, DIM, RESET = "\033[36m", "\033[35m", "\033[2m", "\033[0m"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an experiment TOML.")
    parser.add_argument("experiment", help="path to an experiment .toml")
    args = parser.parse_args()

    exp = load_experiment(args.experiment)
    if len(exp.bots) < 2:
        raise SystemExit("Experiment needs at least bot1 and bot2.")

    # Models/personas/task come from the experiment; ollama_url + num_ctx are the
    # machine settings, so they come from config.toml.
    cfg = get_config()

    bots = [
        Bot(name=name, persona=spec.read_persona(), model=spec.model, body=spec.body)
        for name, spec in exp.bots.items()
    ]
    colour_of = {bots[0].name: C1, bots[1].name: C2}

    logger = RunLogger(
        task=exp.task, turn_limit=exp.turn_limit, stop_marker=exp.stop_marker
    )

    def turn_fn(bot: Bot, messages: list[dict[str, str]]) -> str:
        colour = colour_of.get(bot.name, "")
        print(f"\n{colour}[{bot.name} · {bot.body} · {bot.model}]{RESET}")
        stats: dict = {}

        async def collect() -> str:
            parts: list[str] = []
            async for piece in stream_chat(
                ollama_url=cfg.ollama_url,
                model=bot.model,
                system=bot.persona,
                messages=messages,
                num_ctx=cfg.num_ctx,
                on_stats=stats.update,
            ):
                parts.append(piece)
                print(f"{colour}{piece}{RESET}", end="", flush=True)
            print()
            return "".join(parts)

        t0 = time.perf_counter()
        text = asyncio.run(collect())
        latency = time.perf_counter() - t0

        logger.add_turn(
            bot=bot.name,
            model=bot.model,
            persona=bot.persona,
            text=text,
            latency_s=latency,
            tokens=stats.get("eval_count"),
        )
        return text

    print(f"{DIM}TASK: {exp.task}{RESET}")
    transcript = run_conversation(
        task=exp.task,
        bots=bots,
        turn_fn=turn_fn,
        max_turns=exp.turn_limit,
        stop_marker=exp.stop_marker,
    )

    path = logger.save(converged=transcript.converged)
    tag = "converged early" if transcript.converged else "hit turn limit"
    print(f"\n{DIM}--- done ({len(transcript.turns)} turns, {tag}) ---{RESET}")
    print(f"{DIM}saved: {path}{RESET}")

    if exp.judge:
        judge_model = exp.judge_model or bots[0].model
        judgment = judge_service.judge_run(
            turns=logger.turns,
            task=exp.task,
            converged=transcript.converged,
            stop_marker=exp.stop_marker,
            ollama_url=cfg.ollama_url,
            model=judge_model,
            num_ctx=cfg.num_ctx,
        )
        run_logger.append_judge(path.stem, judgment)
        led = judgment.get("leader_heuristic")
        print(f"{DIM}judge: converged={judgment['converged']} led={led}"
              f" (model judge: {judge_model}){RESET}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
