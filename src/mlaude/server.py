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
from mlaude.config import CONTEXT_MESSAGES, MEMORY_PATH
from mlaude.llm import OllamaProvider, load_system_prompt
from mlaude.memory import ensure_memory, load_memory, overwrite_memory
from mlaude.observer import RagChunk, RagRecord, RequestTrace
from mlaude.rag import KnowledgeBase
from mlaude.tools import UpdateMemoryTool, WebSearchTool
from mlaude.tools_base import ToolEvent, ToolRegistry

logger = logging.getLogger("mlaude")

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.llm = OllamaProvider()

    registry = ToolRegistry()
    registry.register(WebSearchTool())
    registry.register(UpdateMemoryTool())
    app.state.registry = registry

    ensure_memory()

    kb = KnowledgeBase()
    chunk_count = kb.index_all()
    if chunk_count:
        logger.info("RAG ready: %d chunks indexed", chunk_count)
    app.state.kb = kb

    yield


app = FastAPI(title="mlaude", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
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
                await ws.send_json({"type": "session_created", "session_id": session_id})

            elif msg_type == "list_sessions":
                sessions = await db.list_sessions()
                await ws.send_json({"type": "sessions", "data": sessions})

            elif msg_type == "load_session":
                session_id = msg.get("session_id", "")
                if not await db.session_exists(session_id):
                    await ws.send_json({"type": "error", "content": "Session not found"})
                    continue
                messages = await db.get_messages(session_id)
                await ws.send_json({"type": "history", "session_id": session_id, "messages": messages})

            elif msg_type == "delete_session":
                session_id = msg.get("session_id", "")
                await db.delete_session(session_id)
                await ws.send_json({"type": "session_deleted", "session_id": session_id})

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

            elif msg_type == "message":
                session_id = msg.get("session_id", "")
                content = msg.get("content", "").strip()
                if not content:
                    continue

                if not session_id or not await db.session_exists(session_id):
                    session_id = await db.create_session()
                    await ws.send_json({"type": "session_created", "session_id": session_id})

                await db.add_message(session_id, "user", content)

                history = await db.get_messages(session_id, limit=CONTEXT_MESSAGES)
                llm_messages = [{"role": m["role"], "content": m["content"]} for m in history]

                # --- Build trace ---
                trace = RequestTrace(session_id=session_id)
                trace.history_messages = len(llm_messages)

                # --- RAG retrieval ---
                rag_chunks: list[dict] = []
                if kb.collection.count() > 0:
                    rag_start = time.monotonic()
                    rag_chunks = kb.query(content, n=5)
                    rag_ms = int((time.monotonic() - rag_start) * 1000)
                    trace.rag = RagRecord(
                        query=content,
                        chunks=[RagChunk(text=c["text"], source=c["source"], score=c["score"]) for c in rag_chunks],
                        duration_ms=rag_ms,
                    )

                # --- System prompt ---
                system = load_system_prompt(rag_context=rag_chunks if rag_chunks else None)

                # --- Token estimates for trace ---
                system_chars = len(system)
                history_chars = sum(len(m["content"]) for m in llm_messages)
                trace.system_prompt_tokens = system_chars // 4
                trace.context_tokens = (system_chars + history_chars) // 4
                trace.memory_tokens = (
                    len(MEMORY_PATH.read_text()) // 4 if MEMORY_PATH.exists() else 0
                )

                # --- Stream with tools ---
                full_response = ""
                try:
                    async for event in llm.stream_with_tools(system, llm_messages, registry, trace=trace):
                        if isinstance(event, ToolEvent):
                            await ws.send_json({
                                "type": f"tool_{event.phase}",
                                "tool": event.tool_name,
                                "input": event.tool_input,
                                "output": event.tool_output,
                            })
                        else:
                            full_response += event
                            await ws.send_json({"type": "token", "content": event})
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
                        await ws.send_json({"type": "title_updated", "session_id": session_id, "title": title})
                    except Exception:
                        pass

    except WebSocketDisconnect:
        pass
