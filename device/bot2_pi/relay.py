#!/usr/bin/env python3
"""Venus Bot 2 body + relay — a SELF-CONTAINED single file for the Raspberry Pi.

Nothing here imports from the laptop's brain/ code. It talks to the brain only
over HTTP, using values from config.json. Copy this whole folder to the Pi and
follow SETUP.md.

What it does:
  * Connects to the laptop brain's GET /watch (SSE) over the tailnet and follows
    the live conversation.
  * DISPLAYS Bot 2's turns  -> this Pi is Bot 2's body (printed to stdout / log).
  * FORWARDS Bot 1's turns  -> served to the ESP32 over local WiFi at GET /latest.
  * Accepts a human line from the ESP32 at POST /line and assigns it as a new
    task by POSTing the brain's /run (draining the stream to drive it).

So: ESP32  <--local WiFi-->  Pi (this relay)  <--tailnet-->  laptop brain.

Only dependency: requests  (see requirements.txt).
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests

CONFIG_PATH = Path(__file__).with_name("config.json")


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise SystemExit(
            f"Missing {CONFIG_PATH.name}. Copy config.example.json to config.json "
            "and fill in the laptop's tailnet address + API key."
        )
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


class State:
    """Shared state: the latest Bot-1 turn to hand the ESP32."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.seq = 0
        self.bot = ""
        self.text = ""

    def set_latest(self, bot: str, text: str) -> None:
        with self._lock:
            self.seq += 1
            self.bot = bot
            self.text = text

    def snapshot(self) -> dict:
        with self._lock:
            return {"seq": self.seq, "bot": self.bot, "text": self.text}


class Relay:
    def __init__(self, cfg: dict) -> None:
        self.brain = cfg["brain_url"].rstrip("/")
        self.key = cfg["api_key"]
        self.display_bot = cfg.get("display_bot", "bot2")  # this Pi is bot2's body
        self.forward_bot = cfg.get("forward_bot", "bot1")  # forward to the ESP32
        self.turn_limit = int(cfg.get("turn_limit", 8))
        self.stop_marker = cfg.get("stop_marker", "CONVERGED")
        self.state = State()

    # --- brain client -----------------------------------------------------
    def _auth(self) -> dict:
        return {"Authorization": f"Bearer {self.key}"}

    def watch_forever(self) -> None:
        """Follow GET /watch (SSE) and react to each event; reconnect on drop."""
        url = f"{self.brain}/watch"
        while True:
            try:
                print(f"[relay] connecting to {url}")
                with requests.get(url, headers=self._auth(), stream=True, timeout=(10, None)) as r:
                    r.raise_for_status()
                    print("[relay] watching live runs")
                    for raw in r.iter_lines(decode_unicode=True):
                        if not raw or raw.startswith(":"):
                            continue  # keepalive / comment
                        if raw.startswith("data:"):
                            self._on_event(json.loads(raw[5:].strip()))
            except Exception as exc:  # network hiccup, brain restart, etc.
                print(f"[relay] watch dropped ({exc}); retrying in 3s")
                time.sleep(3)

    def _on_event(self, ev: dict) -> None:
        et = ev.get("type")
        if et == "turn_end":
            bot = ev.get("bot")
            text = ev.get("text", "")
            if bot == self.display_bot:
                # This Pi is Bot 2's body: show Bot 2's turn.
                print(f"\n=== BOT 2 (this Pi) ===\n{text}\n")
            elif bot == self.forward_bot:
                # Hand Bot 1's turn to the ESP32 (it polls GET /latest).
                self.state.set_latest(bot, text)
                print(f"[relay] forwarded {bot} turn to ESP32 (seq {self.state.snapshot()['seq']})")
        elif et == "done":
            print(f"[relay] run finished (converged={ev.get('converged')})")
        elif et == "error":
            print(f"[relay] brain error: {ev.get('message')}")

    def assign_task(self, task: str) -> None:
        """A line typed on the ESP32 becomes a new task. POST /run and drain it
        so the brain produces turns (which come back to us via /watch)."""
        body = {"task": task, "turn_limit": self.turn_limit, "stop_marker": self.stop_marker}
        try:
            with requests.post(f"{self.brain}/run", headers=self._auth(),
                               json=body, stream=True, timeout=(10, None)) as r:
                r.raise_for_status()
                for _ in r.iter_lines():
                    pass  # events are handled via /watch; just drive the run
        except Exception as exc:
            print(f"[relay] failed to assign task: {exc}")


def make_handler(relay: Relay):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # quieter logs
            pass

        def _json(self, code: int, payload: dict) -> None:
            data = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            if self.path == "/health":
                self._json(200, {"status": "ok"})
            elif self.path == "/latest":
                # The ESP32 polls this and prints new Bot 1 turns to Serial.
                self._json(200, relay.state.snapshot())
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self) -> None:
            if self.path != "/line":
                self._json(404, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                text = json.loads(raw).get("text", "").strip()
            except json.JSONDecodeError:
                text = raw.decode("utf-8", "replace").strip()
            if not text:
                self._json(400, {"error": "empty line"})
                return
            print(f"[relay] task from ESP32: {text!r}")
            threading.Thread(target=relay.assign_task, args=(text,), daemon=True).start()
            self._json(202, {"accepted": text})

    return Handler


def main() -> None:
    # Line-buffer stdout so turns and logs appear live (piped output / journald).
    try:
        import sys
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    cfg = load_config()
    relay = Relay(cfg)

    host = cfg.get("listen_host", "0.0.0.0")
    port = int(cfg.get("listen_port", 8100))
    server = ThreadingHTTPServer((host, port), make_handler(relay))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"[relay] ESP32-facing server on http://{host}:{port} (GET /latest, POST /line)")

    relay.watch_forever()  # blocks, reconnecting as needed


if __name__ == "__main__":
    main()
