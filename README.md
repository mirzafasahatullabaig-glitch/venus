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

**From source (dev):**

```powershell
cd F:\venus\brain
..\.venv\Scripts\python.exe serve.py                 # cockpit at http://127.0.0.1:8080
..\.venv\Scripts\python.exe run_experiment.py experiments/example.toml
```

Or use the VS Code tasks (Terminal → Run Task → "Venus: …").

By default the brain binds `127.0.0.1` (localhost only). To let the Pi and other
devices reach it over the tailnet, set `host` in `config.toml` to the laptop's
tailnet IP (e.g. `100.76.45.98`) or `0.0.0.0`, then relaunch. Ollama stays
localhost-only; only this app port is exposed, and it requires the API key.

## Building venus.exe

```powershell
.\.venv\Scripts\pip install pyinstaller
.\.venv\Scripts\pyinstaller.exe build\venus.spec --distpath dist --workpath build\_work --clean --noconfirm
```

Output is `dist\venus.exe` (~14 MB, one file). On first launch it writes a
`config.toml` next to itself from the bundled template, then asks you to set a
real `api_key` and relaunch. `web/` and `personas/` are baked into the exe;
`config.toml` stays beside it so you can edit it without rebuilding.

### Unblocking the unsigned exe (Windows Defender / SmartScreen)

The exe is unsigned, so Windows may warn on first run:

- **SmartScreen** ("Windows protected your PC"): click **More info → Run anyway**.
- **"Downloaded from the internet" block**: right-click `venus.exe` →
  **Properties** → tick **Unblock** → **OK**. Or in PowerShell:
  ```powershell
  Unblock-File .\dist\venus.exe
  ```
- If Defender quarantines it, add an exclusion for the folder
  (Windows Security → Virus & threat protection → Manage settings → Exclusions),
  or run from source instead.
