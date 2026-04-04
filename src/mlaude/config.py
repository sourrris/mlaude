"""Centralized configuration for Mlaude."""

import os
from pathlib import Path

MLAUDE_HOME = Path.home() / ".mlaude"
SESSIONS_DB = MLAUDE_HOME / "sessions.db"
MEMORY_PATH = MLAUDE_HOME / "MEMORY.md"
KNOWLEDGE_DIR = MLAUDE_HOME / "knowledge"
CHROMADB_DIR = MLAUDE_HOME / "chromadb"

OLLAMA_MODEL = "qwen2.5:14b-instruct-q4_K_M"
OLLAMA_URL = "http://localhost:11434"
EMBEDDING_MODEL = "nomic-embed-text"

SOUL_PATH = Path(__file__).resolve().parent.parent.parent / "SOUL.md"
KNOWLEDGE_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge"

CONTEXT_MESSAGES = 20  # how many past messages to send to the LLM

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")


def ensure_dirs():
    MLAUDE_HOME.mkdir(exist_ok=True)
    KNOWLEDGE_DIR.mkdir(exist_ok=True)
