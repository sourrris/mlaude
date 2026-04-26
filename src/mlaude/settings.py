from __future__ import annotations

import os
from pathlib import Path


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
APP_HOME = Path(os.environ.get("MLAUDE_HOME", PROJECT_ROOT / ".local" / "mlaude"))
DATA_DIR = APP_HOME / "workspace"
FILES_DIR = DATA_DIR / "files"
INDEX_DIR = DATA_DIR / "index"
PLAYWRIGHT_DIR = APP_HOME / "playwright"
PLAYWRIGHT_PROFILE_DIR = PLAYWRIGHT_DIR / "profile"
PLAYWRIGHT_OUTPUT_DIR = PLAYWRIGHT_DIR / "output"

DATABASE_URL = os.environ.get(
    "MLAUDE_DATABASE_URL",
    f"sqlite+aiosqlite:///{(DATA_DIR / 'mlaude.db').as_posix()}",
)

# Use MLAUDE_LLM_BASE_URL as the primary setting for the LLM runtime base URL
LLM_BASE_URL = os.environ.get("MLAUDE_LLM_BASE_URL", "http://127.0.0.1:1234")
DEFAULT_CHAT_MODEL = os.environ.get("MLAUDE_DEFAULT_CHAT_MODEL", "gemma4:e4b")
DEFAULT_EMBEDDING_MODEL = os.environ.get(
    "MLAUDE_DEFAULT_EMBEDDING_MODEL",
    "text-embedding-nomic-embed-text-v1.5",
)
DEFAULT_TEMPERATURE = float(os.environ.get("MLAUDE_DEFAULT_TEMPERATURE", "0.2"))

MAX_HISTORY_MESSAGES = int(os.environ.get("MLAUDE_MAX_HISTORY_MESSAGES", "18"))
MAX_SEARCH_RESULTS = int(os.environ.get("MLAUDE_MAX_SEARCH_RESULTS", "6"))
MAX_FILE_READ_CHARS = int(os.environ.get("MLAUDE_MAX_FILE_READ_CHARS", "16000"))
PYTHON_TOOL_TIMEOUT_SECONDS = int(
    os.environ.get("MLAUDE_PYTHON_TOOL_TIMEOUT_SECONDS", "12")
)
PLAYWRIGHT_ENABLED = _truthy(os.environ.get("MLAUDE_PLAYWRIGHT_ENABLED", "true"))
PLAYWRIGHT_BROWSER = os.environ.get("MLAUDE_PLAYWRIGHT_BROWSER", "chrome")
PLAYWRIGHT_HEADLESS = _truthy(os.environ.get("MLAUDE_PLAYWRIGHT_HEADLESS", "false"))
PLAYWRIGHT_SEARCH_ENGINE = os.environ.get("MLAUDE_PLAYWRIGHT_SEARCH_ENGINE", "google")
PLAYWRIGHT_MAX_STEPS = int(os.environ.get("MLAUDE_PLAYWRIGHT_MAX_STEPS", "12"))
PLAYWRIGHT_TOOL_TIMEOUT_SECONDS = int(
    os.environ.get("MLAUDE_PLAYWRIGHT_TOOL_TIMEOUT_SECONDS", "30")
)

ENABLE_TEST_RUNTIME = _truthy(os.environ.get("MLAUDE_ENABLE_TEST_RUNTIME"))

CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "MLAUDE_CORS_ORIGINS",
        ",".join(
            [
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://localhost:3001",
                "http://127.0.0.1:3001",
                "http://localhost:4175",
                "http://127.0.0.1:4175",
            ]
        ),
    ).split(",")
    if origin.strip()
]


def ensure_app_dirs() -> None:
    for path in (
        APP_HOME,
        DATA_DIR,
        FILES_DIR,
        INDEX_DIR,
        PLAYWRIGHT_DIR,
        PLAYWRIGHT_PROFILE_DIR,
        PLAYWRIGHT_OUTPUT_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)
