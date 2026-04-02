"""Centralized configuration for Mlaude."""

from pathlib import Path

MLAUDE_HOME = Path.home() / ".mlaude"
SESSIONS_DB = MLAUDE_HOME / "sessions.db"

OLLAMA_MODEL = "llama3.1:8b-instruct-q4_K_M"
OLLAMA_URL = "http://localhost:11434"

SOUL_PATH = Path(__file__).resolve().parent.parent.parent / "SOUL.md"

CONTEXT_MESSAGES = 20  # how many past messages to send to the LLM


def ensure_dirs():
    MLAUDE_HOME.mkdir(exist_ok=True)
