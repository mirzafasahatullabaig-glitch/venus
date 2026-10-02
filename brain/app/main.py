"""FastAPI wiring ONLY: mount the routers. No business logic lives here.

Run from the brain/ directory:
    uvicorn app.main:app --host 127.0.0.1 --port 8080
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import ASSET_DIR
from app.routes import health, run, turn, watch

app = FastAPI(title="Venus brain", version="1.0.0")

# API routes first — they take precedence over the "/" static mount below.
app.include_router(health.router)
app.include_router(turn.router)
app.include_router(run.router)
app.include_router(watch.router)

# The cockpit UI at "/". Mounted last so it doesn't shadow the API routes.
WEB_DIR = ASSET_DIR / "web"
if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
