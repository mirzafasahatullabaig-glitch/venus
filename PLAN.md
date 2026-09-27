# Venus — Build Plan

**Two Embodied Bots on a Shared Brain.**
A phase-by-phase build guide to follow in VS Code with Claude Code.

> Save this file anywhere (e.g. `F:\venus\PLAN.md`) and keep it beside the repo.
> Work one phase at a time. Each session: "do the next phase from PLAN.md."

---

## 1. The idea

Two individual bots — **ESP32-S3 (Bot 1)** and **Raspberry Pi 3/Zero (Bot 2)**, each with its own persona — hold a conversation and collaborate on tasks you assign. Neither device runs an LLM. The **laptop is the shared brain**: it hosts Ollama + the models, runs the conversation loop, and serves a cockpit where you assign work and watch the bots collaborate live.

**Research goal:** what happens when two genuinely different minds (different models, different bodies) cooperate through conversation.

## 2. Why it's different

- Software multi-agent frameworks have the conversation but run on one machine — **no bodies**.
- ESP32 + Pi + Ollama projects use devices as sensors feeding one LLM — **no conversation**.
- **Venus embodies the conversation:** two physical devices, two different minds, cooperating.

## 3. Hardware & the 8 GB decision

| Device | Role | Runs a model? |
|---|---|---|
| Laptop (RTX 5050, **8 GB VRAM**) | Shared brain + cockpit | Yes |
| ESP32-S3 (COM6, no OS) | Bot 1's body | No — borrows the brain |
| Raspberry Pi 3/Zero | Bot 2's body + network relay | No — borrows the brain |

**Model decision — two 3B models resident at once:**
- Pair: **`llama3.2:3b` (Bot 1) + `qwen2.5:3b` (Bot 2)** — different families = different minds.
- Budget: ~4 GB weights (Q4) + ~1–2 GB KV cache + ~1–1.5 GB overhead ≈ **6–7.5 GB** → fits 8 GB.
- Keep **Q4** quant, `num_ctx ≈ 4096`, and set `OLLAMA_KEEP_ALIVE=-1`, `OLLAMA_MAX_LOADED_MODELS=2`.
- **Verify** on the real machine: `ollama ps` / `nvidia-smi` after loading both.

**Network:** ESP32 can't run Tailscale → the **Pi is the relay** (ESP32 → Pi over local WiFi → laptop over the tailnet). Tailscale **Funnel** is a backup direct path. Ollama stays **localhost-only**; the laptop app (port 8080) is the only exposed port and enforces an **API key**.

---

## 4. Structure — strict separation (nothing collides)

**Core principle: one concern = one module/folder. No file does two jobs.** Each layer talks to the next only through a defined interface, so you can change one without breaking the others.

```
venus/
├── PLAN.md                     # this file
├── README.md                   # how to run/build (points to PLAN.md for the roadmap)
├── .gitignore
│
├── brain/                      # THE LAPTOP APP — the only place models are touched
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py             # FastAPI wiring ONLY (routes → services). No logic here.
│   │   ├── config.py           # loads config.toml + experiment TOMLs. Nothing else reads files.
│   │   ├── security.py         # API-key check ONLY.
│   │   └── routes/
│   │       ├── health.py       # GET /health
│   │       ├── turn.py         # POST /turn  (one model turn)
│   │       └── run.py          # POST /run, stream a full conversation
│   │
│   ├── core/                   # PURE LOGIC — no FastAPI, no I/O, unit-testable alone
│   │   ├── __init__.py
│   │   ├── bot.py              # Bot = persona + model id + body id (a data class)
│   │   ├── conversation.py     # the turn-taking loop + stop conditions
│   │   └── transcript.py       # the shared transcript object
│   │
│   ├── services/               # ADAPTERS to the outside world (each isolates ONE dependency)
│   │   ├── __init__.py
│   │   ├── ollama_client.py    # the ONLY file that talks to Ollama
│   │   └── run_logger.py       # the ONLY file that writes to runs/
│   │
│   ├── personas/               # the two identities — plain text, easy to edit
│   │   ├── bot1_esp32.txt
│   │   └── bot2_pi.txt
│   │
│   ├── experiments/            # one TOML = one reproducible experiment
│   │   └── example.toml
│   │
│   ├── web/                    # the cockpit UI (kept fully separate from Python logic)
│   │   ├── index.html
│   │   ├── app.js
│   │   └── style.css
│   │
│   ├── config.example.toml     # template (committed) → copy to config.toml (gitignored)
│   └── requirements.txt
│
├── firmware/
│   └── bot1_esp32/             # Bot 1's body — Arduino, self-contained
│       ├── bot1_esp32.ino
│       └── secrets.h.example   # template → copy to secrets.h (gitignored)
│
├── device/
│   └── bot2_pi/                # Bot 2 — a SELF-CONTAINED mini-project, paste-ready onto the Pi
│       ├── relay.py            # single-file relay/driver — no imports from brain/
│       ├── requirements.txt    # the Pi's OWN deps (kept apart from brain/requirements.txt)
│       ├── config.example.json # the Pi's OWN config → copy to config.json on the Pi
│       ├── venus-bot2.service  # optional systemd unit to run it on the Pi
│       └── SETUP.md            # exact copy-paste commands, top to bottom, to stand it up
│
├── analysis/                   # study the runs — never imports from brain/
│   └── compare_runs.py
│
├── build/
│   └── venus.spec              # PyInstaller
│
├── .vscode/
│   ├── tasks.json              # run / build tasks
│   └── launch.json             # debug
│
└── runs/                       # saved transcripts (GITIGNORED — data, not code)
```

**The rules that keep things from colliding:**
1. **`core/` is pure** — it knows nothing about FastAPI, Ollama, or files. It's just the conversation logic. You can test it with fake inputs.
2. **`services/` isolates each external dependency** — only `ollama_client.py` talks to Ollama; only `run_logger.py` writes files. Swap either without touching logic.
3. **`app/` only wires** — routes call services and core; no business logic lives in a route.
4. **`web/` is separate from Python** — the UI is its own files, talking to the brain only over HTTP.
5. **Each device is self-contained** — `firmware/bot1_esp32/` and `device/bot2_pi/` don't depend on each other, and neither imports from `brain/`. The Pi folder is its **own mini-project**: its own `relay.py`, its own `requirements.txt`, its own `config.json`, and a `SETUP.md` with exact copy-paste commands. You keep it in the repo for version control, but everything in it is written to be dropped onto the Pi **as-is** — the Pi never needs the laptop's Python environment or any `brain/` file. This keeps the two codebases from getting messy or tangled.
6. **Config and secrets are centralized and gitignored** — `config.py` is the only reader; secrets live in `.example` templates you copy locally.
7. **`runs/` is data, not code** — gitignored, written only by `run_logger.py`, read only by `analysis/`.

---

## PHASE 0 — Project setup

**Goal:** empty, well-structured repo open in VS Code.

1. Create `venus/` (e.g. under `F:\venus`), open in VS Code, drop this `PLAN.md` in the root.
2. Have Claude Code scaffold the structure in section 4 (empty files + `__init__.py`s).
3. `git init`; write `.gitignore`: `config.toml`, `secrets.h`, `runs/`, `dist/`, `build/`, `__pycache__/`, `.venv/`.
4. Create a venv; fill `brain/requirements.txt`: `fastapi`, `uvicorn`, `httpx`, `tomli` (py<3.11).
5. Write `brain/config.example.toml`: `api_key`, `port=8080`, `ollama_url`, model pair, `num_ctx=4096`.

**Done when:** repo opens cleanly, venv activates, `pip install -r brain/requirements.txt` succeeds.

## PHASE 1 — Brain substrate (single turns work)

**Goal:** the laptop produces one persona-shaped model turn on demand.

1. `services/ollama_client.py`: call Ollama `/api/chat` with {model, system prompt, messages, num_ctx}, stream the reply, keep-alive on. **Only this file imports httpx/knows Ollama.**
2. `app/security.py`: the Bearer-key check.
3. `app/routes/health.py`: `GET /health` (no auth).
4. `app/routes/turn.py`: `POST /turn` {persona, transcript, model} → streamed reply.
5. `app/main.py`: wire the routes + middleware. `app/config.py`: load `config.toml`.
6. Pull models: `ollama pull llama3.2:3b`, `ollama pull qwen2.5:3b`.
7. **VRAM check:** load both, `ollama ps` — confirm both resident, total < 8 GB.

**Done when:** `curl` to `/turn` returns a sensible streamed answer; both models stay loaded.

## PHASE 2 — Conversation loop (two bots talk, in the terminal)

**Goal:** two bots hold a coherent back-and-forth on a task, in the terminal.

1. `core/bot.py`: `Bot` data class (persona text + model id + body id).
2. `core/transcript.py`: the shared transcript (append + render for the next turn).
3. `core/conversation.py`: the loop — alternate Bot 1 → Bot 2, append each reply, stop on turn limit. **Pure logic; it calls a "turn function" passed in, not Ollama directly.**
4. Write `personas/bot1_esp32.txt` and `personas/bot2_pi.txt` (start: proposer vs. critic/refiner).
5. A small runner script wires `conversation.py` to `ollama_client.py` and prints the transcript.

**Done when:** the two bots produce a coherent, on-topic, non-repetitive exchange for N turns.

## PHASE 3 — Research affordances (runs become data)

**Goal:** every run saved and reproducible.

1. `services/run_logger.py`: write `runs/<timestamp>.json` — task + per turn {bot, model, persona, text, latency, tokens}.
2. `experiments/example.toml`: models, personas, task, turn limit. `config.py` loads it.
3. Stop condition beyond turn limit: a bot can emit a "converged" marker to end early.
4. (Optional) a judge pass appended to the run file (did they converge? who led?).

**Done when:** running an experiment TOML produces a saved, reproducible transcript with metadata.

## PHASE 4 — Cockpit UI (assign & watch)

**Goal:** assign a task in the browser, watch the bots collaborate live.

1. `web/index.html` + `app.js` + `style.css`: task box, start/stop, turn-limit + persona fields, **two-color transcript** (Bot 1 vs Bot 2) streaming.
2. `app/routes/run.py`: `POST /run` streams turns (SSE or polling) to the page.
3. `main.py` serves `web/` at `/`. Show per-turn model + timing; list past runs.

**Done when:** you type a task, hit go, and watch the labeled conversation stream in the browser.

## PHASE 5 — Package as the executable

**Goal:** the brain ships as `venus.exe`, launched on demand.

1. `build/venus.spec`: PyInstaller `--onefile`, bundle `web/` + `personas/`; read bundled assets via `_MEIPASS`.
2. `.vscode/tasks.json`: build task + run task.
3. Build → double-click test → reads `config.toml` beside it → cockpit reachable.
4. README: how to unblock the unsigned exe (Windows Defender/SmartScreen).

**Done when:** double-clicking `venus.exe` starts the brain and serves the cockpit.

## PHASE 6 — Different models per bot (the research core)

**Goal:** two genuinely different minds — different models, both resident, live.

1. Assign `llama3.2:3b` → Bot 1, `qwen2.5:3b` → Bot 2 in an experiment TOML.
2. Confirm both stay resident during alternating turns (`ollama ps`); tune `num_ctx` if tight.
3. Run the **same task with different pairings/personas**, one variable at a time; compare saved runs.
4. `analysis/compare_runs.py`: does the weaker model adapt? how do disagreements resolve? does asymmetry predict who "wins"?

**Done when:** you can run and compare experiments with two different resident models.

## PHASE 7 — Bring in the bodies (ESP32 + Pi)

**Goal:** the bots are embodied on their devices and reachable from any network.

1. `firmware/bot1_esp32/bot1_esp32.ino`: over Serial, show Bot 1's turns; let you feed a line back. WiFi + target + key in `secrets.h`.
2. **Build the Pi as a self-contained unit** in `device/bot2_pi/` — `relay.py` (single file, no `brain/` imports), `requirements.txt`, `config.example.json`, `venus-bot2.service`, and `SETUP.md`. Write it so the whole folder can be copied onto the Pi and run with nothing from the laptop repo.
3. **On the Pi (from SETUP.md, copy-paste):** install Tailscale + sign in; copy `device/bot2_pi/` to the Pi (e.g. `scp` or a `git clone` of just that folder); `pip install -r requirements.txt`; copy `config.example.json` → `config.json` and fill in the laptop's tailnet address + API key; run `relay.py` (or enable the systemd service). The Pi acts as the **relay** (ESP32 → Pi → laptop over the tailnet) and shows Bot 2's turns.
4. Test the full path from a different WiFi. Keep **Funnel** as the laptop-direct backup.

**Done when:** a task assigned at the laptop runs with the ESP32 and Pi as the two bots' bodies, off-LAN — and the Pi was stood up purely by copying `device/bot2_pi/` and following `SETUP.md`, with nothing borrowed from `brain/`.

---

## Phase 8+ (parked)

- **Asymmetric embodied abilities:** ESP32-bot senses/acts (sensor, LED, relay, OLED); Pi-bot computes/stores/searches — they must cooperate because neither can do the other's job.
- Physical world enters the chat (a sensor reading becomes a turn).
- Bots act on conclusions (relay/motor/display).
- Move Bot 2's turn-driving onto the Pi (device autonomy).
- Tools / function calling; memory across runs; message schemas between bots.
- Bigger/asymmetric models via reload (offline) or a second inference host.
- Abuse guards on the public path.

## Reference

- Models: llama3.2:3b, qwen2.5:7b, llama3.1:8b, qwen2.5-coder:7b, qwen2.5:14b (all tool-calling). Also pull **qwen2.5:3b**.
- Cold-load ~50 s once per idle model; warm ~0.5 s. Two resident 3B models avoid per-turn reloads.
- Ollama endpoints: `/api/chat`, `/v1/chat/completions`, `/api/tags`.
- Tailscale: `100.76.45.98`, `laptop-fmteceol`, `*.tail8e47e5.ts.net`.
- Keep Ollama localhost-only; laptop app on 8080 is the only exposed port.

## How to work this plan in Claude Code

1. Approve the folder structure first.
2. Build **one phase at a time** (0 → 7). At each phase end, run the "Done when" check before moving on.
3. Keep secrets in gitignored files with `.example` templates committed.
4. Keep the separation rules in section 4 — never let one file take on a second job.
