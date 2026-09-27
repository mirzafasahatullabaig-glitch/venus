"""Study saved runs. Reads runs/*.json directly; never imports from brain/.

    python compare_runs.py                 # compare every run in runs/
    python compare_runs.py a.json b.json   # compare specific runs
    python compare_runs.py --detail a.json # one run, per-turn + metrics

The metrics are deliberately simple and their meaning is stated where computed;
they are research signals to eyeball, not verdicts.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

RUNS_DIR = Path(__file__).resolve().parent.parent / "runs"

_WORD = re.compile(r"[a-z0-9]+")


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def load(path_or_name: str) -> dict:
    p = Path(path_or_name)
    if not p.suffix:
        p = RUNS_DIR / f"{p.name}.json"
    elif not p.is_absolute() and not p.exists():
        p = RUNS_DIR / p.name
    rec = json.loads(p.read_text(encoding="utf-8"))
    rec["_name"] = p.stem
    return rec


def all_runs() -> list[dict]:
    if not RUNS_DIR.exists():
        return []
    return [load(str(p)) for p in sorted(RUNS_DIR.glob("*.json"))]


def bots_in(rec: dict) -> list[str]:
    seen: list[str] = []
    for t in rec.get("turns", []):
        if t["bot"] not in seen:
            seen.append(t["bot"])
    return seen


def metrics(rec: dict) -> dict:
    """Per-run summary + per-bot stats + two rough research signals."""
    turns = rec.get("turns", [])
    bots = bots_in(rec)

    per_bot: dict[str, dict] = {}
    for b in bots:
        bt = [t for t in turns if t["bot"] == b]
        words = [w for t in bt for w in _words(t["text"])]
        toks = [t["tokens"] for t in bt if t.get("tokens") is not None]
        lats = [t["latency_s"] for t in bt if t.get("latency_s") is not None]
        per_bot[b] = {
            "model": bt[0]["model"] if bt else "?",
            "turns": len(bt),
            "words": len(words),
            "tokens": sum(toks) if toks else None,
            "avg_latency_s": round(sum(lats) / len(lats), 2) if lats else None,
        }

    total_words = sum(pb["words"] for pb in per_bot.values()) or 1
    for b, pb in per_bot.items():
        pb["word_share"] = round(pb["words"] / total_words, 2)

    # Who declared convergence (contained the stop marker in a turn)?
    marker = rec.get("stop_marker")
    declared_by = None
    if marker:
        for t in turns:
            if marker in t["text"]:
                declared_by = t["bot"]
                break

    # Rough "adaptation" proxy: for each bot, Jaccard overlap between the content
    # words of its LAST turn and ALL of the OTHER bot's EARLIER turns. Higher =
    # this bot ended up echoing the other's vocabulary more. A signal, not proof.
    adaptation: dict[str, float] = {}
    for b in bots:
        others = [t for t in turns if t["bot"] != b]
        mine = [t for t in turns if t["bot"] == b]
        if not others or not mine:
            continue
        other_vocab = {w for t in others for w in _words(t["text"])}
        last_vocab = set(_words(mine[-1]["text"]))
        if not last_vocab:
            continue
        inter = len(last_vocab & other_vocab)
        union = len(last_vocab | other_vocab) or 1
        adaptation[b] = round(inter / union, 2)

    return {
        "name": rec.get("_name"),
        "task": rec.get("task", ""),
        "converged": rec.get("converged", False),
        "turns": len(turns),
        "turn_limit": rec.get("turn_limit"),
        "declared_convergence": declared_by,
        "per_bot": per_bot,
        "adaptation": adaptation,
    }


def print_detail(rec: dict) -> None:
    m = metrics(rec)
    print(f"\nRUN {m['name']}")
    print(f"  task: {m['task'][:90]}")
    print(f"  turns: {m['turns']}/{m['turn_limit']}  converged: {m['converged']}"
          f"  declared_by: {m['declared_convergence']}")
    print("  per bot:")
    for b, pb in m["per_bot"].items():
        print(f"    {b:5} {pb['model']:14} turns={pb['turns']} words={pb['words']}"
              f" share={pb['word_share']} tokens={pb['tokens']}"
              f" avg_latency={pb['avg_latency_s']}s")
    if m["adaptation"]:
        print("  adaptation (last-turn vocab overlap with the other bot):")
        for b, v in m["adaptation"].items():
            print(f"    {b:5} {v}")
    print("  transcript:")
    for t in rec.get("turns", []):
        head = t["text"].strip().replace("\n", " ")
        print(f"    [{t['index']}] {t['bot']}: {head[:100]}")


def print_compare(recs: list[dict]) -> None:
    rows = [metrics(r) for r in recs]
    print(f"\n{'run':<18}{'conv':<6}{'turns':<7}{'declared':<10}"
          f"{'bot1 model':<14}{'b1 share':<9}{'bot2 model':<14}{'b2 share':<9}")
    print("-" * 87)
    for m in rows:
        pb = m["per_bot"]
        bots = list(pb.keys())
        b1 = pb.get(bots[0]) if len(bots) > 0 else None
        b2 = pb.get(bots[1]) if len(bots) > 1 else None
        print(f"{(m['name'] or '')[:17]:<18}"
              f"{('yes' if m['converged'] else 'no'):<6}"
              f"{m['turns']:<7}"
              f"{str(m['declared_convergence'] or '-'):<10}"
              f"{(b1['model'] if b1 else '-'):<14}{(b1['word_share'] if b1 else '-'):<9}"
              f"{(b2['model'] if b2 else '-'):<14}{(b2['word_share'] if b2 else '-'):<9}")
    print(f"\n{len(rows)} run(s). Use --detail <run> for one run's turns + metrics.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare Venus runs.")
    ap.add_argument("runs", nargs="*", help="run files or names; default = all in runs/")
    ap.add_argument("--detail", metavar="RUN", help="show one run in detail")
    args = ap.parse_args()

    if args.detail:
        print_detail(load(args.detail))
        return 0

    recs = [load(r) for r in args.runs] if args.runs else all_runs()
    if not recs:
        print("No runs found. Run an experiment first (brain/run_experiment.py).")
        return 1
    print_compare(recs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
