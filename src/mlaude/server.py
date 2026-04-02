"""FastAPI app with WebSocket streaming."""

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from mlaude import db
from mlaude.config import CONTEXT_MESSAGES
from mlaude.llm import OllamaProvider, load_system_prompt

logger = logging.getLogger("mlaude")

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.llm = OllamaProvider()
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

            elif msg_type == "message":
                session_id = msg.get("session_id", "")
                content = msg.get("content", "").strip()
                if not content:
                    continue

                # Create session if needed
                if not session_id or not await db.session_exists(session_id):
                    session_id = await db.create_session()
                    await ws.send_json({"type": "session_created", "session_id": session_id})

                # Save user message
                await db.add_message(session_id, "user", content)

                # Build context
                history = await db.get_messages(session_id, limit=CONTEXT_MESSAGES)
                llm_messages = [{"role": m["role"], "content": m["content"]} for m in history]
                system = load_system_prompt()

                # Stream response
                full_response = ""
                try:
                    async for token in llm.stream(system, llm_messages):
                        full_response += token
                        await ws.send_json({"type": "token", "content": token})
                except Exception as e:
                    logger.exception("LLM streaming error")
                    await ws.send_json({"type": "error", "content": f"LLM error: {e}"})
                    continue

                # Save assistant message
                if full_response:
                    await db.add_message(session_id, "assistant", full_response)

                await ws.send_json({"type": "done", "session_id": session_id})

                # Auto-generate title for first exchange
                messages = await db.get_messages(session_id)
                if len(messages) == 2:  # first user + first assistant
                    try:
                        title = await llm.generate_title(content, full_response)
                        await db.update_session_title(session_id, title)
                        await ws.send_json({"type": "title_updated", "session_id": session_id, "title": title})
                    except Exception:
                        pass

    except WebSocketDisconnect:
        pass
