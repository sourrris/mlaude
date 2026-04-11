"""FastAPI app with WebSocket streaming + tool system + RAG + observability."""

import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from mlaude import db
from mlaude.config import (
    CHROMADB_DIR,
    CONTEXT_MESSAGES,
    EMBEDDING_MODEL,
    KNOWLEDGE_DIR,
    KNOWLEDGE_TEMPLATES_DIR,
    MEMORY_PATH,
    MLAUDE_HOME,
    OLLAMA_MODEL,
    OLLAMA_URL,
)
from mlaude.llm import OllamaProvider, load_system_prompt
from mlaude.memory import ensure_memory, load_memory, overwrite_memory
from mlaude.observer import CONTEXT_LIMIT, LOGS_DIR, RagChunk, RagRecord, RequestTrace
from mlaude.rag import KnowledgeBase
from mlaude.tools import DeleteMemoryFactTool, UpdateMemoryTool, WebSearchTool
from mlaude.tools_base import ToolEvent, ToolRegistry

logger = logging.getLogger("mlaude")

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"


def _copy_knowledge_templates() -> int:
    """Copy knowledge template files to KNOWLEDGE_DIR if they don't already exist.

    Never overwrites user-edited files — only copies files that are absent.
    Returns count of files copied.
    """
    if not KNOWLEDGE_TEMPLATES_DIR.exists():
        return 0

    copied = 0
    for src in KNOWLEDGE_TEMPLATES_DIR.rglob("*.md"):
        relative = src.relative_to(KNOWLEDGE_TEMPLATES_DIR)
        dest = KNOWLEDGE_DIR / relative
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(src.read_text())
            copied += 1

    if copied:
        logger.info("Copied %d knowledge template(s) to %s", copied, KNOWLEDGE_DIR)
    return copied


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.llm = OllamaProvider()

    registry = ToolRegistry()
    registry.register(WebSearchTool())
    registry.register(UpdateMemoryTool())
    registry.register(DeleteMemoryFactTool())
    app.state.registry = registry

    ensure_memory()
    _copy_knowledge_templates()

    kb = KnowledgeBase()
    chunk_count = kb.index_all()
    if chunk_count:
        logger.info("RAG ready: %d chunks indexed", chunk_count)
    app.state.kb = kb

    yield


def _available_trace_dates() -> list[str]:
    """Return sorted list of dates with trace files (newest first)."""
    if not LOGS_DIR.exists():
        return []
    dates = []
    for f in LOGS_DIR.glob("trace-*.jsonl"):
        date_str = f.stem.replace("trace-", "")
        dates.append(date_str)
    return sorted(dates, reverse=True)


def _load_traces(date: str, limit: int) -> dict:
    """Load traces from JSONL log file for a given date."""
    dates = _available_trace_dates()
    if not date and dates:
        date = dates[0]

    traces: list[dict] = []
    log_path = LOGS_DIR / f"trace-{date}.jsonl"
    if log_path.exists():
        lines = log_path.read_text().strip().splitlines()
        # Read newest first
        for line in reversed(lines[-limit:]):
            try:
                traces.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    return {
        "type": "traces",
        "date": date,
        "dates_available": dates,
        "traces": traces,
        "total": len(traces),
    }


def _chromadb_stats(kb: KnowledgeBase) -> dict:
    """Get ChromaDB collection stats."""
    chunk_count = kb.collection.count()
    knowledge_files: list[dict] = []
    if KNOWLEDGE_DIR.exists():
        for p in sorted(KNOWLEDGE_DIR.rglob("*.md")):
            relative = str(p.relative_to(KNOWLEDGE_DIR))
            parts = Path(relative).parts
            top = parts[0].lower() if parts else ""
            if top == "about":
                stype = "about"
            elif top in ("interests", "interest"):
                stype = "interest"
            elif top in ("behavior", "behaviour"):
                stype = "behavior"
            else:
                stype = "general"
            knowledge_files.append({"path": relative, "source_type": stype})

    return {
        "type": "chromadb_stats",
        "collection_name": "knowledge",
        "chunk_count": chunk_count,
        "knowledge_files": knowledge_files,
        "knowledge_dir": str(KNOWLEDGE_DIR),
        "chromadb_dir": str(CHROMADB_DIR),
    }


def _system_info() -> dict:
    """Get system configuration info."""
    memory_size = 0
    memory_tokens = 0
    if MEMORY_PATH.exists():
        memory_size = MEMORY_PATH.stat().st_size
        memory_tokens = memory_size // 4

    knowledge_count = (
        len(list(KNOWLEDGE_DIR.rglob("*.md"))) if KNOWLEDGE_DIR.exists() else 0
    )

    return {
        "type": "system_info",
        "model": OLLAMA_MODEL,
        "embedding_model": EMBEDDING_MODEL,
        "context_limit": CONTEXT_LIMIT,
        "ollama_url": OLLAMA_URL,
        "memory_path": str(MEMORY_PATH),
        "memory_size_bytes": memory_size,
        "memory_tokens_approx": memory_tokens,
        "knowledge_dir": str(KNOWLEDGE_DIR),
        "knowledge_file_count": knowledge_count,
        "mlaude_home": str(MLAUDE_HOME),
    }


def _aggregate_stats(days: int) -> dict:
    """Aggregate metrics from recent trace files."""
    dates = _available_trace_dates()[:days]
    all_traces: list[dict] = []

    for date in dates:
        log_path = LOGS_DIR / f"trace-{date}.jsonl"
        if log_path.exists():
            for line in log_path.read_text().strip().splitlines():
                try:
                    all_traces.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    if not all_traces:
        return {"type": "diag_stats", "request_count": 0}

    total_ms_vals = [t.get("total_ms", 0) for t in all_traces]
    first_token_vals = [t.get("first_token_ms", 0) for t in all_traces]
    context_pct_vals = [t.get("context_pct", 0) for t in all_traces]

    # Tool call frequency
    tool_counts: dict[str, int] = {}
    for t in all_traces:
        for tc in t.get("tool_calls", []):
            name = tc.get("name", "unknown")
            tool_counts[name] = tool_counts.get(name, 0) + 1

    # Warning frequency
    warning_count = sum(len(t.get("warnings", [])) for t in all_traces)

    # RAG stats
    rag_durations = [t["rag"]["duration_ms"] for t in all_traces if t.get("rag")]
    rag_chunk_counts = [t["rag"]["count"] for t in all_traces if t.get("rag")]

    # Latency buckets
    buckets = {"<1s": 0, "1-5s": 0, "5-15s": 0, "15-30s": 0, ">30s": 0}
    for ms in total_ms_vals:
        if ms < 1000:
            buckets["<1s"] += 1
        elif ms < 5000:
            buckets["1-5s"] += 1
        elif ms < 15000:
            buckets["5-15s"] += 1
        elif ms < 30000:
            buckets["15-30s"] += 1
        else:
            buckets[">30s"] += 1

    n = len(all_traces)
    return {
        "type": "diag_stats",
        "request_count": n,
        "avg_total_ms": sum(total_ms_vals) // n,
        "avg_first_token_ms": sum(first_token_vals) // n,
        "avg_context_pct": sum(context_pct_vals) // n,
        "tool_call_counts": tool_counts,
        "warning_count": warning_count,
        "rag_avg_duration_ms": sum(rag_durations) // len(rag_durations)
        if rag_durations
        else 0,
        "rag_avg_chunks": round(sum(rag_chunk_counts) / len(rag_chunk_counts), 1)
        if rag_chunk_counts
        else 0,
        "latency_buckets": buckets,
    }


app = FastAPI(title="mlaude", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Vite builds assets to static/assets/ but references them as /assets/ in HTML
ASSETS_DIR = STATIC_DIR / "assets"
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/{path:path}")
async def spa_fallback(path: str):
    """Catch-all for SPA client-side routing — serves index.html for any non-API path."""
    # Don't intercept API or WebSocket routes
    if path.startswith("api/") or path.startswith("static/") or path.startswith("ws"):
        from fastapi import HTTPException

        raise HTTPException(status_code=404)
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/status")
async def status():
    llm: OllamaProvider = app.state.llm
    health = await llm.check_status()
    sessions = await db.list_sessions(limit=5)
    return {"ollama": health, "session_count": len(sessions)}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    llm: OllamaProvider = app.state.llm
    registry: ToolRegistry = app.state.registry
    kb: KnowledgeBase = app.state.kb

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "content": "Invalid JSON"})
                continue

            msg_type = msg.get("type")

            if msg_type == "new_session":
                session_id = await db.create_session()
                await ws.send_json(
                    {"type": "session_created", "session_id": session_id}
                )

            elif msg_type == "list_sessions":
                sessions = await db.list_sessions()
                await ws.send_json({"type": "sessions", "data": sessions})

            elif msg_type == "load_session":
                session_id = msg.get("session_id", "")
                if not await db.session_exists(session_id):
                    await ws.send_json(
                        {"type": "error", "content": "Session not found"}
                    )
                    continue
                messages = await db.get_messages(session_id)
                await ws.send_json(
                    {"type": "history", "session_id": session_id, "messages": messages}
                )

            elif msg_type == "delete_session":
                session_id = msg.get("session_id", "")
                await db.delete_session(session_id)
                await ws.send_json(
                    {"type": "session_deleted", "session_id": session_id}
                )

            elif msg_type == "get_memory":
                content = load_memory()
                await ws.send_json({"type": "memory", "content": content})

            elif msg_type == "update_memory_raw":
                raw_content = msg.get("content", "")
                overwrite_memory(raw_content)
                await ws.send_json({"type": "memory_saved"})

            elif msg_type == "reindex":
                chunk_count = kb.index_all()
                await ws.send_json({"type": "reindex_done", "chunks": chunk_count})

            elif msg_type == "get_traces":
                date = msg.get("date", "")
                limit = min(int(msg.get("limit", 100)), 500)
                await ws.send_json(_load_traces(date, limit))

            elif msg_type == "get_chromadb_stats":
                await ws.send_json(_chromadb_stats(kb))

            elif msg_type == "get_system_info":
                await ws.send_json(_system_info())

            elif msg_type == "get_diag_stats":
                days = min(int(msg.get("days", 1)), 7)
                await ws.send_json(_aggregate_stats(days))

            elif msg_type == "message":
                session_id = msg.get("session_id", "")
                content = msg.get("content", "").strip()
                if not content:
                    continue

                if not session_id or not await db.session_exists(session_id):
                    session_id = await db.create_session()
                    await ws.send_json(
                        {"type": "session_created", "session_id": session_id}
                    )

                await db.add_message(session_id, "user", content)

                history = await db.get_messages(session_id, limit=CONTEXT_MESSAGES)
                llm_messages = [
                    {"role": m["role"], "content": m["content"]} for m in history
                ]

                # --- Build trace ---
                trace = RequestTrace(session_id=session_id)
                trace.history_messages = len(llm_messages)

                # --- RAG retrieval ---
                rag_chunks: list[dict] = []
                if kb.collection.count() > 0:
                    # Build conversation context from last 2 turns for better retrieval
                    recent_turns = [
                        m["content"]
                        for m in llm_messages[-4:]
                        if m["role"] in ("user", "assistant")
                    ]
                    conv_ctx = (
                        " ".join(recent_turns[-2:]) if len(recent_turns) >= 2 else None
                    )

                    rag_start = time.monotonic()
                    rag_chunks = kb.query_v2(content, conversation_context=conv_ctx)
                    rag_ms = int((time.monotonic() - rag_start) * 1000)
                    trace.rag = RagRecord(
                        query=content,
                        chunks=[
                            RagChunk(
                                text=c["text"],
                                source=c["source"],
                                source_type=c.get("source_type", "general"),
                                score=c["score"],
                            )
                            for c in rag_chunks
                        ],
                        duration_ms=rag_ms,
                    )

                # --- System prompt ---
                system = load_system_prompt(
                    rag_context=rag_chunks if rag_chunks else None
                )

                # --- Token estimates for trace ---
                system_chars = len(system)
                history_chars = sum(len(m["content"]) for m in llm_messages)
                trace.system_prompt_tokens = system_chars // 4
                trace.context_tokens = (system_chars + history_chars) // 4
                trace.memory_tokens = (
                    len(MEMORY_PATH.read_text()) // 4 if MEMORY_PATH.exists() else 0
                )

                # --- Stream with tools + <think> tag parsing ---
                THINK_OPEN = "<think>"
                THINK_CLOSE = "</think>"
                full_response = ""
                full_thinking = ""
                in_thinking = False
                buf = ""

                try:
                    async for event in llm.stream_with_tools(
                        system, llm_messages, registry, trace=trace
                    ):
                        if isinstance(event, ToolEvent):
                            await ws.send_json(
                                {
                                    "type": f"tool_{event.phase}",
                                    "tool": event.tool_name,
                                    "input": event.tool_input,
                                    "output": event.tool_output,
                                }
                            )
                            continue

                        buf += event

                        # State machine: route tokens to thinking vs. response streams
                        while True:
                            if not in_thinking:
                                if THINK_OPEN in buf:
                                    pre = buf[: buf.index(THINK_OPEN)]
                                    if pre:
                                        full_response += pre
                                        await ws.send_json(
                                            {"type": "token", "content": pre}
                                        )
                                    buf = buf[buf.index(THINK_OPEN) + len(THINK_OPEN) :]
                                    in_thinking = True
                                    await ws.send_json({"type": "thinking_start"})
                                else:
                                    # Flush everything safe (keep tail in case tag spans chunks)
                                    safe = max(0, len(buf) - len(THINK_OPEN) + 1)
                                    if safe > 0:
                                        full_response += buf[:safe]
                                        await ws.send_json(
                                            {"type": "token", "content": buf[:safe]}
                                        )
                                        buf = buf[safe:]
                                    break
                            else:
                                if THINK_CLOSE in buf:
                                    chunk = buf[: buf.index(THINK_CLOSE)]
                                    if chunk:
                                        full_thinking += chunk
                                        print(f"BACKEND THINKING TOKEN: '{chunk}'")
                                        await ws.send_json(
                                            {"type": "thinking_token", "content": chunk}
                                        )
                                    buf = buf[
                                        buf.index(THINK_CLOSE) + len(THINK_CLOSE) :
                                    ]
                                    in_thinking = False
                                    await ws.send_json({"type": "thinking_done"})
                                else:
                                    safe = max(0, len(buf) - len(THINK_CLOSE) + 1)
                                    if safe > 0:
                                        full_thinking += buf[:safe]
                                        await ws.send_json(
                                            {
                                                "type": "thinking_token",
                                                "content": buf[:safe],
                                            }
                                        )
                                        buf = buf[safe:]
                                    break

                        # Flush any remaining buffer
                        if buf.strip():
                            if in_thinking:
                                full_thinking += buf
                                print(f"BACKEND FINAL THINKING BUF: '{buf}'")
                                await ws.send_json(
                                    {"type": "thinking_token", "content": buf}
                                )
                            else:
                                full_response += buf
                                await ws.send_json({"type": "token", "content": buf})

                except Exception as e:
                    logger.exception("LLM streaming error")
                    await ws.send_json({"type": "error", "content": f"LLM error: {e}"})
                    continue

                if full_response:
                    await db.add_message(session_id, "assistant", full_response)

                await ws.send_json({"type": "done", "session_id": session_id})

                # --- Finalize + send trace ---
                trace.finalize(response_text=full_response)
                trace.log()
                await ws.send_json({"type": "trace", "data": trace.to_ws_payload()})

                # Auto-generate title
                messages = await db.get_messages(session_id)
                if len(messages) == 2:
                    try:
                        title = await llm.generate_title(content, full_response)
                        await db.update_session_title(session_id, title)
                        await ws.send_json(
                            {
                                "type": "title_updated",
                                "session_id": session_id,
                                "title": title,
                            }
                        )
                    except Exception:
                        pass

    except WebSocketDisconnect:
        pass
