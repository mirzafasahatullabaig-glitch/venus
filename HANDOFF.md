# Venus — handoff / resume prompt

Paste this into a fresh Claude Code session (working dir `F:\venus`) to resume
with full context. Venus is BUILT and running on real hardware at **v1.0.0**.
Follow `PLAN.md` for the original roadmap; this file is the quick resume + v2 plan.

## The idea
Two bots with distinct personas converse and collaborate on assigned tasks.
Neither device runs an LLM — the LAPTOP is the shared brain (Ollama + models +
FastAPI app + cockpit UI). Bot 1 is embodied on an ESP32-S3; Bot 2 on a
Raspberry Pi (which is also the network relay). Research goal: what happens when
two genuinely different minds (different models, different bodies) cooperate.

## Models (local, via Ollama; both ~3B, resident together under 8 GB VRAM)
- Bot 1 = llama3.2:3b, body "esp32"
- Bot 2 = qwen2.5:3b, body "pi"
- keep_alive=-1, num_ctx=4096. Confirmed ~4.6 GB / 8 GB with both loaded.

## Architecture (strict separation — one concern per module; see PLAN.md §4)
- brain/core/     PURE logic: bot.py, transcript.py, conversation.py
                  (run_conversation sync + stream_conversation async). No I/O.
- brain/services/ adapters: ollama_client.py (ONLY file that talks to Ollama),
                  run_logger.py (ONLY writer of runs/, + list/read/append_judge),
                  judge.py (deterministic + optional model verdict).
- brain/app/      wiring only: main.py, config.py (ONLY config/TOML reader),
                  security.py (Bearer key), hub.py (in-proc event fan-out),
                  routes/ health.py, turn.py, run.py (SSE), watch.py (SSE broadcast).
- brain/web/      cockpit UI (index.html/app.js/style.css), served at /.
- brain/experiments/*.toml  example, same_model, swapped_models.
- brain/personas/ bot1_esp32.txt (proposer), bot2_pi.txt (critic/refiner).
- device/bot2_pi/ SELF-CONTAINED Pi relay (relay.py, requirements.txt=requests,
                  config.example.json, venus-bot2.service, SETUP.md). No brain/ imports.
- firmware/bot1_esp32/ Arduino sketch (.ino) — WiFi to the Pi, Serial for the human.
- analysis/compare_runs.py  reads runs/*.json directly (no brain/ imports).
- build/venus.spec  PyInstaller one-file; serve.py is the entry point.

## What's done (phases 0-7 + judge + configurable host) — live-verified
Brain /health /turn(auth) /run(SSE) /watch(SSE) /runs; cockpit streams a
two-color transcript with per-turn model+tokens+latency, saves+judges runs,
replays past runs. Experiments + run logger + compare_runs + judge all work.
venus.exe builds and serves. Both bodies work: a task from the cockpit OR typed
into the ESP32's Serial Monitor runs a real conversation; ESP32 shows Bot 1,
Pi shows Bot 2. Early-stop marker is "CONVERGED".

## Networking
- Laptop tailnet IP 100.76.45.98; brain on port 8080 (set `host` in config.toml to
  the tailnet IP so the Pi can reach it; firewall rule "Venus brain 8080" allows
  inbound TCP 8080). Ollama stays localhost-only (11434).
- Pi: tailnet 100.94.134.127, LAN 192.168.1.9, relay on port 8100 (GET /latest,
  POST /line). ESP32 reaches the Pi over 2.4 GHz WiFi at 192.168.1.9:8100.
- Flow: ESP32 --WiFi--> Pi --tailnet--> laptop brain. ESP32 never uses Tailscale.

## Config / secrets (gitignored; only .example templates committed)
brain/config.toml (api_key, host, port, ollama_url, num_ctx, [bots.bot1/bot2]),
device/bot2_pi/config.json, firmware/.../secrets.h. NEVER commit real creds — the
secrets.h.example template must stay placeholders.

## How to restart
1. ollama ps   (service auto-starts; both models load on first call)
2. laptop: cd F:\venus\brain && ..\.venv\Scripts\python.exe serve.py
3. Pi:     cd ~/bot2_pi && .venv/bin/python relay.py   (expect "watching live runs")
4. ESP32:  power on; it reconnects. Serial Monitor @ 115200.
Cockpit: http://100.76.45.98:8080/  (paste api_key, Start).

## Backup
GitHub (private): https://github.com/mirzafasahatullabaig-glitch/venus
Remote `origin`. master + tags pushed.

## STANDING RULE — save each version
After every completed change: `git commit`, then `git tag -a vX.Y.Z -m "..."`,
then `git push origin master --tags`, and tell the user the new tag.
(patch = fix, minor = feature, major = breaking/on request.)

## v2 — planned direction (confirm specifics with the user first)
Headline focus chosen: **cockpit polish** + **tools/memory** (user will refine).
Candidate work, pick/confirm before building:
- Cockpit polish: reflect ESP32-assigned tasks live in the browser via the
  existing /watch stream; in-browser run comparison; UI cleanups.
- Tools / memory: give bots tool/function calling; memory across runs (so a bot
  can recall prior conversations). Decide storage + schema with the user.
Also parked from Phase 8: asymmetric embodied abilities (ESP32 senses/acts:
sensor/LED/relay; Pi computes/stores) so the bots MUST cooperate; physical
sensor readings entering the chat; bots acting on conclusions; moving Bot 2's
turn-driving onto the Pi.

Start v2 by asking the user to pin down the first concrete feature, then plan it.
