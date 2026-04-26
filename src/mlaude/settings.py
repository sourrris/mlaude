from __future__ import annotations

import os
from pathlib import Path


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


# ── Paths ──────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ~/.mlaude is the canonical home (like Hermes's ~/.hermes)
MLAUDE_HOME = Path(os.environ.get("MLAUDE_HOME", Path.home() / ".mlaude"))

DATA_DIR = MLAUDE_HOME / "data"
LOGS_DIR = MLAUDE_HOME / "logs"
SKILLS_DIR = MLAUDE_HOME / "skills"

# ── LLM ────────────────────────────────────────────────────────────────────
LLM_BASE_URL = os.environ.get("MLAUDE_LLM_BASE_URL", "http://127.0.0.1:1234")
DEFAULT_CHAT_MODEL = os.environ.get("MLAUDE_DEFAULT_CHAT_MODEL", "gemma4:e4b")
DEFAULT_TEMPERATURE = float(os.environ.get("MLAUDE_DEFAULT_TEMPERATURE", "0.2"))

# ── Agent loop ─────────────────────────────────────────────────────────────
MAX_ITERATIONS = int(os.environ.get("MLAUDE_MAX_ITERATIONS", "50"))
MAX_HISTORY_MESSAGES = int(os.environ.get("MLAUDE_MAX_HISTORY_MESSAGES", "18"))
MAX_SEARCH_RESULTS = int(os.environ.get("MLAUDE_MAX_SEARCH_RESULTS", "6"))
MAX_FILE_READ_CHARS = int(os.environ.get("MLAUDE_MAX_FILE_READ_CHARS", "16000"))
TERMINAL_TIMEOUT_SECONDS = int(
    os.environ.get("MLAUDE_TERMINAL_TIMEOUT_SECONDS", "120")
)
PYTHON_TOOL_TIMEOUT_SECONDS = int(
    os.environ.get("MLAUDE_PYTHON_TOOL_TIMEOUT_SECONDS", "12")
)

DEFAULT_SYSTEM_PROMPT = os.environ.get(
    "MLAUDE_SYSTEM_PROMPT",
    (
        "You are mlaude, a powerful AI coding assistant running locally.\n\n"
        "You have access to tools for file operations, terminal commands, "
        "web search, browser automation, and more.\n\n"
        "Rules:\n"
        "- Use tools to gather information before answering when needed.\n"
        "- Be concise and directly responsive.\n"
        "- When writing code, prefer clean, well-documented implementations.\n"
        "- If you're unsure, say so rather than guessing.\n"
    ),
)


def ensure_app_dirs() -> None:
    for path in (
        MLAUDE_HOME,
        DATA_DIR,
        LOGS_DIR,
        SKILLS_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)
