"""SQLite session store with WAL mode and FTS5 search.

Inspired by Hermes ``hermes_state.py``.  Provides persistent storage for
agent sessions, messages, and full-text search across conversation history.

All operations are synchronous (thread-safe via write lock + jitter retry).
"""

from __future__ import annotations

import json
import logging
import random
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mlaude.settings import MLAUDE_HOME

logger = logging.getLogger(__name__)

_DB_PATH = MLAUDE_HOME / "data" / "sessions.db"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionDB:
    """Thread-safe SQLite session store."""

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or _DB_PATH)
        self._write_lock = threading.Lock()
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _write_with_retry(self, fn, max_retries: int = 5):
        """Execute a write operation with jitter retry on lock contention."""
        for attempt in range(max_retries):
            try:
                with self._write_lock:
                    conn = self._connect()
                    try:
                        result = fn(conn)
                        conn.commit()
                        return result
                    finally:
                        conn.close()
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < max_retries - 1:
                    jitter = random.uniform(0.05, 0.2) * (attempt + 1)
                    time.sleep(jitter)
                else:
                    raise

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        def _create(conn: sqlite3.Connection):
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT DEFAULT '',
                    platform TEXT DEFAULT 'cli',
                    model TEXT DEFAULT '',
                    parent_session_id TEXT,
                    root_session_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    ended_at TEXT,
                    total_tokens INTEGER DEFAULT 0,
                    total_cost REAL DEFAULT 0.0,
                    metadata TEXT DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT DEFAULT '',
                    tool_calls TEXT,
                    tool_call_id TEXT,
                    tool_name TEXT,
                    reasoning TEXT,
                    tokens INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_messages_session
                    ON messages(session_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_sessions_updated
                    ON sessions(updated_at DESC);
            """)

            # FTS5 virtual table for full-text search
            try:
                conn.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
                    USING fts5(content, session_id, content=messages, content_rowid=rowid)
                """)
            except sqlite3.OperationalError:
                pass  # FTS5 may not be available on all builds

            # Best-effort migrations for older DBs
            for col_def in (
                "parent_session_id TEXT",
                "root_session_id TEXT",
            ):
                try:
                    conn.execute(f"ALTER TABLE sessions ADD COLUMN {col_def}")
                except sqlite3.OperationalError:
                    pass

        self._write_with_retry(_create)

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def create_session(
        self,
        session_id: str | None = None,
        platform: str = "cli",
        model: str = "",
        title: str = "",
        parent_session_id: str | None = None,
    ) -> str:
        sid = session_id or uuid.uuid4().hex
        now = _now_iso()
        root_session_id = parent_session_id or sid

        def _insert(conn):
            conn.execute(
                "INSERT INTO sessions "
                "(id, title, platform, model, parent_session_id, root_session_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (sid, title, platform, model, parent_session_id, root_session_id, now, now),
            )
            return sid

        return self._write_with_retry(_insert)

    def end_session(self, session_id: str) -> None:
        now = _now_iso()

        def _end(conn):
            conn.execute(
                "UPDATE sessions SET ended_at=?, updated_at=? WHERE id=?",
                (now, now, session_id),
            )

        self._write_with_retry(_end)

    def get_session(self, session_id: str) -> dict | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM sessions WHERE id=?", (session_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_sessions(
        self,
        limit: int = 20,
        platform: str | None = None,
    ) -> list[dict]:
        conn = self._connect()
        try:
            if platform:
                rows = conn.execute(
                    "SELECT * FROM sessions WHERE platform=? ORDER BY updated_at DESC LIMIT ?",
                    (platform, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def resolve_session_id(self, session_id_prefix: str) -> str | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT id FROM sessions WHERE id LIKE ? ORDER BY updated_at DESC LIMIT 1",
                (f"{session_id_prefix}%",),
            ).fetchone()
            return str(row["id"]) if row else None
        finally:
            conn.close()

    def create_continuation_session(self, source_session_id: str, title: str = "") -> str:
        source = self.get_session(source_session_id)
        if source is None:
            raise ValueError(f"Session not found: {source_session_id}")
        return self.create_session(
            platform=source.get("platform", "cli"),
            model=source.get("model", ""),
            title=title or source.get("title", ""),
            parent_session_id=source_session_id,
        )

    def update_session_title(self, session_id: str, title: str) -> None:
        def _update(conn):
            conn.execute(
                "UPDATE sessions SET title=?, updated_at=? WHERE id=?",
                (title, _now_iso(), session_id),
            )

        self._write_with_retry(_update)

    def update_session_tokens(
        self, session_id: str, tokens: int, cost: float = 0.0
    ) -> None:
        def _update(conn):
            conn.execute(
                "UPDATE sessions SET total_tokens=total_tokens+?, "
                "total_cost=total_cost+?, updated_at=? WHERE id=?",
                (tokens, cost, _now_iso(), session_id),
            )

        self._write_with_retry(_update)

    def delete_session(self, session_id: str) -> bool:
        def _delete(conn):
            cursor = conn.execute(
                "DELETE FROM sessions WHERE id=?", (session_id,)
            )
            return cursor.rowcount > 0

        return self._write_with_retry(_delete)

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str = "",
        tool_calls: list[dict] | None = None,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
        reasoning: str | None = None,
        tokens: int = 0,
    ) -> str:
        msg_id = uuid.uuid4().hex
        now = _now_iso()

        def _insert(conn):
            conn.execute(
                "INSERT INTO messages "
                "(id, session_id, role, content, tool_calls, tool_call_id, "
                "tool_name, reasoning, tokens, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    msg_id, session_id, role, content,
                    json.dumps(tool_calls) if tool_calls else None,
                    tool_call_id, tool_name, reasoning, tokens, now,
                ),
            )
            # Update session timestamp
            conn.execute(
                "UPDATE sessions SET updated_at=? WHERE id=?",
                (now, session_id),
            )
            # Update FTS index
            try:
                if content:
                    conn.execute(
                        "INSERT INTO messages_fts(rowid, content, session_id) "
                        "VALUES (last_insert_rowid(), ?, ?)",
                        (content, session_id),
                    )
            except sqlite3.OperationalError:
                pass  # FTS may not be available
            return msg_id

        return self._write_with_retry(_insert)

    def get_messages(
        self,
        session_id: str,
        limit: int | None = None,
    ) -> list[dict]:
        conn = self._connect()
        try:
            if limit:
                rows = conn.execute(
                    "SELECT * FROM messages WHERE session_id=? "
                    "ORDER BY created_at LIMIT ?",
                    (session_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM messages WHERE session_id=? "
                    "ORDER BY created_at",
                    (session_id,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_openai_messages(self, session_id: str) -> list[dict]:
        """Return messages in OpenAI-format for conversation resume."""
        raw_messages = self.get_messages(session_id)
        result: list[dict] = []

        for msg in raw_messages:
            m: dict[str, Any] = {"role": msg["role"]}

            if msg["role"] == "tool":
                m["content"] = msg["content"] or ""
                if msg["tool_call_id"]:
                    m["tool_call_id"] = msg["tool_call_id"]
                if msg["tool_name"]:
                    m["name"] = msg["tool_name"]
            elif msg["role"] == "assistant" and msg.get("tool_calls"):
                m["content"] = msg["content"] or ""
                try:
                    m["tool_calls"] = json.loads(msg["tool_calls"])
                except (json.JSONDecodeError, TypeError):
                    pass
            else:
                m["content"] = msg["content"] or ""

            result.append(m)

        return result

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search_sessions(self, query: str, limit: int = 10) -> list[dict]:
        """Full-text search across message content."""
        conn = self._connect()
        try:
            try:
                rows = conn.execute(
                    "SELECT DISTINCT s.* FROM sessions s "
                    "JOIN messages_fts fts ON fts.session_id = s.id "
                    "WHERE messages_fts MATCH ? "
                    "ORDER BY s.updated_at DESC LIMIT ?",
                    (query, limit),
                ).fetchall()
                return [dict(r) for r in rows]
            except sqlite3.OperationalError:
                # Fallback: LIKE search
                rows = conn.execute(
                    "SELECT DISTINCT s.* FROM sessions s "
                    "JOIN messages m ON m.session_id = s.id "
                    "WHERE m.content LIKE ? "
                    "ORDER BY s.updated_at DESC LIMIT ?",
                    (f"%{query}%", limit),
                ).fetchall()
                return [dict(r) for r in rows]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        conn = self._connect()
        try:
            session_count = conn.execute(
                "SELECT COUNT(*) FROM sessions"
            ).fetchone()[0]
            message_count = conn.execute(
                "SELECT COUNT(*) FROM messages"
            ).fetchone()[0]
            total_tokens = conn.execute(
                "SELECT COALESCE(SUM(total_tokens), 0) FROM sessions"
            ).fetchone()[0]
            return {
                "sessions": session_count,
                "messages": message_count,
                "total_tokens": total_tokens,
            }
        finally:
            conn.close()
