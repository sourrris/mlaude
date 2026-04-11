"""Per-request observability — traces tool calls, RAG, memory, timing, and warnings."""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from mlaude.config import KNOWLEDGE_DIR, MLAUDE_HOME

logger = logging.getLogger("mlaude")

LOGS_DIR = MLAUDE_HOME / "logs"
CONTEXT_LIMIT = 32768          # qwen3.5:9b context window (tokens)
CONTEXT_WARN_PCT = 80          # warn above this %
CONTEXT_CRIT_PCT = 90          # critical above this %

# Phrases that signal the model answered without current data
_STALE_PHRASES = (
    "as of my knowledge",
    "as of my last",
    "as of my training",
    "i don't have access to real-time",
    "i don't have real-time",
    "my knowledge cutoff",
    "i cannot browse",
    "i'm unable to access the internet",
    "i cannot access the internet",
)


@dataclass
class ToolCallRecord:
    name: str
    args: dict
    result: str
    error: bool
    duration_ms: int


@dataclass
class RagChunk:
    text: str
    source: str
    score: float  # lower = more similar (ChromaDB cosine distance)
    source_type: str = "general"  # about | interest | behavior | general


@dataclass
class RagRecord:
    query: str
    chunks: list[RagChunk]
    duration_ms: int

    @property
    def count(self) -> int:
        return len(self.chunks)


@dataclass
class RequestTrace:
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    session_id: str = ""

    # Context
    system_prompt_tokens: int = 0
    history_messages: int = 0
    context_tokens: int = 0

    # RAG
    rag: RagRecord | None = None

    # Tools
    tool_calls: list[ToolCallRecord] = field(default_factory=list)

    # Memory
    memory_tokens: int = 0
    memory_writes: list[str] = field(default_factory=list)

    # Response
    response_tokens: int = 0
    first_token_ms: int = 0
    total_ms: int = 0

    # Populated by finalize()
    warnings: list[str] = field(default_factory=list)
    context_pct: int = 0

    def finalize(self, response_text: str = "") -> None:
        """Compute derived metrics and detect warning conditions."""
        self.context_pct = int((self.context_tokens / CONTEXT_LIMIT) * 100)
        self.response_tokens = len(response_text) // 4

        # Warning: context utilization
        if self.context_pct >= CONTEXT_CRIT_PCT:
            self.warnings.append(
                f"Context critical: {self.context_pct}% of limit — clear history or reduce knowledge chunks"
            )
        elif self.context_pct >= CONTEXT_WARN_PCT:
            self.warnings.append(
                f"Context high: {self.context_pct}% of limit — consider clearing old sessions"
            )

        # Warning: RAG query itself failed (not just filtered by relevance threshold)
        # 0 chunks after threshold filtering is normal for unrelated queries

        # Warning: tool call errors
        for tc in self.tool_calls:
            if tc.error:
                self.warnings.append(f"Tool '{tc.name}' failed: {tc.result[:80]}")

        # Warning: same tool called multiple times
        from collections import Counter
        tool_counts = Counter(tc.name for tc in self.tool_calls)
        for name, count in tool_counts.items():
            if count > 2:
                self.warnings.append(f"Tool '{name}' called {count}x — possible loop")

        # Warning: hallucination signal
        # Model answered factually without searching, using stale-data phrases
        search_called = any(tc.name == "web_search" for tc in self.tool_calls)
        if not search_called and response_text:
            lower = response_text.lower()
            for phrase in _STALE_PHRASES:
                if phrase in lower:
                    self.warnings.append(
                        "Possible stale answer — model acknowledged data limits but did not call web_search"
                    )
                    break

    def _rag_tokens(self) -> int:
        """Approximate token count for all RAG chunks."""
        if not self.rag:
            return 0
        return sum(len(c.text) // 4 for c in self.rag.chunks)

    def log(self) -> None:
        """Append trace as a JSON line to the daily log file."""
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            today = datetime.now().strftime("%Y-%m-%d")
            log_path = LOGS_DIR / f"trace-{today}.jsonl"
            record = {
                "ts": datetime.now().isoformat(),
                "request_id": self.request_id,
                "session_id": self.session_id,
                "system_prompt_tokens": self.system_prompt_tokens,
                "context_tokens": self.context_tokens,
                "context_pct": self.context_pct,
                "history_messages": self.history_messages,
                "memory_tokens": self.memory_tokens,
                "memory_writes": self.memory_writes,
                "rag": {
                    "query": self.rag.query,
                    "count": self.rag.count,
                    "duration_ms": self.rag.duration_ms,
                    "rag_tokens": self._rag_tokens(),
                    "sources": [c.source for c in self.rag.chunks],
                    "scores": [round(c.score, 4) for c in self.rag.chunks],
                    "chunks": [
                        {
                            "source": c.source,
                            "source_type": c.source_type,
                            "score": round(c.score, 4),
                            "preview": c.text[:120],
                        }
                        for c in self.rag.chunks
                    ],
                } if self.rag else None,
                "tool_calls": [
                    {
                        "name": tc.name,
                        "args": tc.args,
                        "result_preview": tc.result[:300] if tc.result else "",
                        "duration_ms": tc.duration_ms,
                        "error": tc.error,
                    }
                    for tc in self.tool_calls
                ],
                "first_token_ms": self.first_token_ms,
                "total_ms": self.total_ms,
                "response_tokens": self.response_tokens,
                "warnings": self.warnings,
            }
            with log_path.open("a") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.warning("Failed to write trace log: %s", e)

    def to_ws_payload(self) -> dict:
        """Serialize for sending over WebSocket."""
        return {
            "request_id": self.request_id,
            "session_id": self.session_id,
            "system_prompt_tokens": self.system_prompt_tokens,
            "context_tokens": self.context_tokens,
            "context_pct": self.context_pct,
            "context_limit": CONTEXT_LIMIT,
            "history_messages": self.history_messages,
            "memory_tokens": self.memory_tokens,
            "memory_writes": self.memory_writes,
            "rag": {
                "query": self.rag.query,
                "count": self.rag.count,
                "duration_ms": self.rag.duration_ms,
                "rag_tokens": self._rag_tokens(),
                "chunks": [
                    {
                        "source": c.source,
                        "source_type": c.source_type,
                        "score": round(c.score, 3),
                        "preview": c.text[:120],
                    }
                    for c in self.rag.chunks
                ],
            } if self.rag else None,
            "tool_calls": [
                {
                    "name": tc.name,
                    "args": tc.args,
                    "result_preview": tc.result[:300] if tc.result else "",
                    "duration_ms": tc.duration_ms,
                    "error": tc.error,
                }
                for tc in self.tool_calls
            ],
            "first_token_ms": self.first_token_ms,
            "total_ms": self.total_ms,
            "response_tokens": self.response_tokens,
            "warnings": self.warnings,
        }
