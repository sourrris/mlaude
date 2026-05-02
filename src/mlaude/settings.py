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
SKINS_DIR = MLAUDE_HOME / "skins"
CONFIG_FILE = MLAUDE_HOME / "config.yaml"

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
        SKINS_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    """Load user config from ~/.mlaude/config.yaml."""
    if not CONFIG_FILE.exists():
        return {}
    try:
        import yaml
        return yaml.safe_load(CONFIG_FILE.read_text()) or {}
    except Exception:
        return {}


def save_config_value(key: str, value) -> None:
    """Set a single top-level key in config.yaml."""
    config = load_config()
    parts = key.split(".")
    d = config
    for part in parts[:-1]:
        d = d.setdefault(part, {})
    d[parts[-1]] = value
    try:
        import yaml
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(yaml.dump(config, default_flow_style=False))
    except Exception:
        pass
