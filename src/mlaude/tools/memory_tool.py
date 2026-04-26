"""Memory tool — persistent cross-session memory.

Simple key-value memory stored in SQLite at ``~/.mlaude/data/memory.db``.
The agent can store and retrieve facts that persist across sessions.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from mlaude.settings import MLAUDE_HOME
from mlaude.tools.registry import registry, tool_error, tool_result

_MEMORY_DB = MLAUDE_HOME / "data" / "memory.db"


def _ensure_memory_db() -> sqlite3.Connection:
    _MEMORY_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_MEMORY_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY,
            key TEXT UNIQUE NOT NULL,
            value TEXT NOT NULL,
            category TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def _memory(action: str, key: str = "", value: str = "",
            category: str = "", task_id: str = None) -> str:
    """Manage persistent memory."""
    conn = _ensure_memory_db()
    now = datetime.now(timezone.utc).isoformat()

    try:
        if action == "store":
            if not key or not value:
                return tool_error("Both key and value are required for store.")
            conn.execute(
                "INSERT INTO memories (id, key, value, category, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=?, category=?, updated_at=?",
                (uuid.uuid4().hex, key, value, category, now, now,
                 value, category, now),
            )
            conn.commit()
            return tool_result({"action": "stored", "key": key})

        elif action == "recall":
            if key:
                row = conn.execute(
                    "SELECT * FROM memories WHERE key=?", (key,)
                ).fetchone()
                if row:
                    return tool_result({
                        "key": row[1], "value": row[2],
                        "category": row[3], "updated_at": row[5],
                    })
                return tool_error(f"Memory not found: {key}")
            else:
                # List all memories
                rows = conn.execute(
                    "SELECT key, value, category, updated_at FROM memories "
                    "ORDER BY updated_at DESC LIMIT 50"
                ).fetchall()
                memories = [
                    {"key": r[0], "value": r[1][:100], "category": r[2]}
                    for r in rows
                ]
                return tool_result({"memories": memories, "total": len(memories)})

        elif action == "forget":
            if not key:
                return tool_error("Key is required for forget.")
            cursor = conn.execute("DELETE FROM memories WHERE key=?", (key,))
            conn.commit()
            return tool_result({"action": "forgotten", "key": key, "deleted": cursor.rowcount > 0})

        elif action == "search":
            query = key or value
            if not query:
                return tool_error("Search query required (pass as key or value).")
            rows = conn.execute(
                "SELECT key, value, category FROM memories "
                "WHERE key LIKE ? OR value LIKE ? LIMIT 20",
                (f"%{query}%", f"%{query}%"),
            ).fetchall()
            return tool_result({
                "query": query,
                "results": [{"key": r[0], "value": r[1][:200], "category": r[2]} for r in rows],
            })

        return tool_error(f"Unknown action: {action}")
    finally:
        conn.close()


registry.register(
    name="memory",
    toolset="memory",
    schema={
        "name": "memory",
        "description": (
            "Persistent memory that survives across sessions. Use 'store' to save facts, "
            "'recall' to retrieve them, 'forget' to delete, 'search' to find."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["store", "recall", "forget", "search"],
                    "description": "Action to perform.",
                },
                "key": {
                    "type": "string",
                    "description": "Memory key (for store/recall/forget) or search query.",
                },
                "value": {
                    "type": "string",
                    "description": "Value to store (for store action).",
                },
                "category": {
                    "type": "string",
                    "description": "Optional category tag.",
                },
            },
            "required": ["action"],
        },
    },
    handler=lambda args, **kw: _memory(
        action=args.get("action", ""),
        key=args.get("key", ""),
        value=args.get("value", ""),
        category=args.get("category", ""),
        task_id=kw.get("task_id"),
    ),
)
