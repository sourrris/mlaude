"""SQLite session and message persistence."""

import uuid
from contextlib import asynccontextmanager

import aiosqlite

from mlaude.config import SESSIONS_DB, ensure_dirs

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);
"""

_initialized = False


@asynccontextmanager
async def _connect():
    global _initialized
    ensure_dirs()
    async with aiosqlite.connect(str(SESSIONS_DB)) as conn:
        conn.row_factory = aiosqlite.Row
        if not _initialized:
            await conn.executescript(_SCHEMA)
            _initialized = True
        yield conn


async def create_session(title: str | None = None) -> str:
    session_id = uuid.uuid4().hex[:12]
    async with _connect() as conn:
        await conn.execute(
            "INSERT INTO sessions (id, title) VALUES (?, ?)",
            (session_id, title or "New chat"),
        )
        await conn.commit()
    return session_id


async def add_message(session_id: str, role: str, content: str):
    async with _connect() as conn:
        await conn.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content),
        )
        await conn.execute(
            "UPDATE sessions SET updated_at = datetime('now') WHERE id = ?",
            (session_id,),
        )
        await conn.commit()


async def get_messages(session_id: str, limit: int = 50) -> list[dict]:
    async with _connect() as conn:
        cursor = await conn.execute(
            "SELECT role, content, created_at FROM messages "
            "WHERE session_id = ? ORDER BY created_at ASC LIMIT ?",
            (session_id, limit),
        )
        rows = await cursor.fetchall()
        return [{"role": r["role"], "content": r["content"], "created_at": r["created_at"]} for r in rows]


async def list_sessions(limit: int = 30) -> list[dict]:
    async with _connect() as conn:
        cursor = await conn.execute(
            "SELECT id, title, created_at, updated_at FROM sessions "
            "ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [
            {"id": r["id"], "title": r["title"], "created_at": r["created_at"], "updated_at": r["updated_at"]}
            for r in rows
        ]


async def update_session_title(session_id: str, title: str):
    async with _connect() as conn:
        await conn.execute("UPDATE sessions SET title = ? WHERE id = ?", (title, session_id))
        await conn.commit()


async def session_exists(session_id: str) -> bool:
    async with _connect() as conn:
        cursor = await conn.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,))
        return await cursor.fetchone() is not None


async def delete_session(session_id: str):
    async with _connect() as conn:
        await conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        await conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await conn.commit()
