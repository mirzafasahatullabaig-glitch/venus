"""A Bot is an identity: a persona + which model drives it + which body wears it.

Pure data. Knows nothing about Ollama, FastAPI, or files.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Bot:
    name: str  # stable id used in the transcript, e.g. "bot1"
    persona: str  # system-prompt text shaping this bot's turns
    model: str  # model id, e.g. "llama3.2:3b"
    body: str  # which body wears it, e.g. "esp32" / "pi"
