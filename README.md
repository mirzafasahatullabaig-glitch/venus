# Venus — Two Embodied Bots on a Shared Brain

Two individual bots — an **ESP32-S3** (Bot 1) and a **Raspberry Pi** (Bot 2), each
with its own persona — hold a conversation and collaborate on tasks you assign.
Neither device runs an LLM. The **laptop is the shared brain**: it hosts Ollama +
the models, runs the conversation loop, and serves a cockpit where you assign work
and watch the bots collaborate live.

> **Roadmap lives in [PLAN.md](PLAN.md).** Work one phase at a time.
> This README covers how to run and build; PLAN.md covers what to build next.

## Layout

- `brain/` — the laptop app (FastAPI + cockpit). The only place models are touched.
- `firmware/bot1_esp32/` — Bot 1's body (Arduino, self-contained).
- `device/bot2_pi/` — Bot 2's body + network relay (self-contained mini-project for the Pi).
- `analysis/` — study saved runs.
- `runs/` — saved transcripts (gitignored data).

See PLAN.md §4 for the separation rules that keep these from colliding.

## Setup (Phase 0)

```powershell
# from the repo root (F:\venus)
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r brain\requirements.txt

# local config (gitignored) from the committed template
Copy-Item brain\config.example.toml brain\config.toml
# then edit brain\config.toml and set a real api_key
```

## Running

Comes online in Phase 1 (`/health`, `/turn`) and Phase 4 (the cockpit at `/`).
See PLAN.md for each phase's "Done when" check.
