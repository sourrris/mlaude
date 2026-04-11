from __future__ import annotations

import asyncio
import json
import re
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mlaude.database import SessionLocal, get_session, init_db
from mlaude.file_service import get_file_or_404, read_file_excerpt, save_upload, serialize_file
from mlaude.models import AppSetting, ChatMessage, ChatSession, MessageFile, StoredFile
from mlaude.retrieval import LocalRetrievalIndex
from mlaude.runtime import BaseRuntime, build_runtime
from mlaude.settings import (
    CORS_ORIGINS,
    DEFAULT_CHAT_MODEL,
    DEFAULT_TEMPERATURE,
    MAX_FILE_READ_CHARS,
    MAX_HISTORY_MESSAGES,
    OLLAMA_BASE_URL,
    PYTHON_TOOL_TIMEOUT_SECONDS,
)


URL_RE = re.compile(r"https?://[^\s]+")
CODE_BLOCK_RE = re.compile(r"```python\s*(.*?)```", re.DOTALL | re.IGNORECASE)
CITATION_RE = re.compile(r"\[(\d+)\]")


class ChatStreamRequest(BaseModel):
    request_id: str
    session_id: str
    content: str
    attachment_ids: list[str] = Field(default_factory=list)
    model: str | None = None
    temperature: float | None = None


class ModelSettingsPayload(BaseModel):
    ollama_base_url: str = OLLAMA_BASE_URL
    default_chat_model: str = DEFAULT_CHAT_MODEL
    temperature: float = DEFAULT_TEMPERATURE


def packet(type_: str, **kwargs: Any) -> dict[str, Any]:
    return {"type": type_, **kwargs}


def json_line(value: dict[str, Any]) -> str:
    return json.dumps(value) + "\n"


def truncate_preview(value: str, limit: int = 140) -> str:
    collapsed = " ".join(value.split())
    return collapsed[:limit].strip() or "New session"


def build_session_title(content: str) -> str:
    return truncate_preview(content, 60)


def build_search_queries(content: str) -> list[str]:
    parts = [content.strip()]
    keywords = re.findall(r"[A-Za-z0-9_]{4,}", content.lower())
    if keywords:
        parts.append(" ".join(keywords[:8]))
    return list(dict.fromkeys(query for query in parts if query))


def extract_python_code(content: str) -> str | None:
    match = CODE_BLOCK_RE.search(content)
    if match:
        return match.group(1).strip()
    if content.lower().startswith("run python:"):
        return content.split(":", 1)[1].strip()
    return None


def wants_file_reader(content: str) -> bool:
    lowered = content.lower()
    return any(phrase in lowered for phrase in ("read file", "quote file", "exact text"))


def build_system_prompt(now: datetime) -> str:
    return (
        "You are a local-first workspace assistant inspired by Onyx. "
        "You help a single user work across their local chats, files, and tool outputs.\n\n"
        "Rules:\n"
        "- Prefer the provided workspace documents and tool outputs when they are relevant.\n"
        "- When using a numbered source document, cite it inline as [n].\n"
        "- Keep the answer grounded, concise, and structured.\n"
        "- If the provided context is insufficient, say so plainly instead of fabricating.\n\n"
        f"Current local date and time: {now.isoformat(timespec='minutes')}"
    )


def build_prompt_documents(documents: list[dict]) -> tuple[list[dict], dict[int, str]]:
    prompt_documents: list[dict] = []
    citation_map: dict[int, str] = {}

    for index, document in enumerate(documents, start=1):
        citation_map[index] = document["document_id"]
        prompt_documents.append(
            {
                "document": index,
                "title": document["title"],
                "source": document["source"],
                "section": document.get("section"),
                "contents": document["content"],
            }
        )

    return prompt_documents, citation_map


def strip_html(value: str) -> str:
    value = re.sub(r"<script.*?</script>", " ", value, flags=re.DOTALL | re.IGNORECASE)
    value = re.sub(r"<style.*?</style>", " ", value, flags=re.DOTALL | re.IGNORECASE)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


async def load_model_settings(db_session: AsyncSession) -> dict[str, Any]:
    record = await db_session.scalar(
        select(AppSetting).where(AppSetting.key == "model_settings")
    )
    payload = {
        "ollama_base_url": OLLAMA_BASE_URL,
        "default_chat_model": DEFAULT_CHAT_MODEL,
        "temperature": DEFAULT_TEMPERATURE,
    }
    if record and record.value:
        payload.update(record.value)
    return payload


async def save_model_settings(
    db_session: AsyncSession, payload: ModelSettingsPayload
) -> dict[str, Any]:
    record = await db_session.scalar(
        select(AppSetting).where(AppSetting.key == "model_settings")
    )
    value = payload.model_dump()
    if record is None:
        record = AppSetting(key="model_settings", value=value)
        db_session.add(record)
    else:
        record.value = value
    await db_session.commit()
    return value


async def serialize_messages(
    db_session: AsyncSession, session_id: str
) -> list[dict[str, Any]]:
    messages = list(
        (
            await db_session.scalars(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at.asc())
            )
        ).all()
    )
    if not messages:
        return []

    attachment_rows = (
        await db_session.execute(
            select(MessageFile.message_id, StoredFile)
            .join(StoredFile, StoredFile.id == MessageFile.file_id)
            .where(MessageFile.message_id.in_([message.id for message in messages]))
            .order_by(StoredFile.created_at.asc())
        )
    ).all()
    attachments: dict[str, list[dict[str, Any]]] = {}
    for message_id, file_record in attachment_rows:
        attachments.setdefault(message_id, []).append(serialize_file(file_record))

    return [
        {
            "id": message.id,
            "session_id": message.session_id,
            "parent_message_id": message.parent_message_id,
            "role": message.role,
            "content": message.content,
            "model_name": message.model_name,
            "packets": message.packets or [],
            "documents": message.documents or [],
            "citations": message.citations or [],
            "meta": message.meta or {},
            "files": attachments.get(message.id, []),
            "created_at": message.created_at.isoformat() if message.created_at else None,
        }
        for message in messages
    ]


async def update_session_preview(
    db_session: AsyncSession,
    *,
    session_obj: ChatSession,
    content: str,
) -> None:
    session_obj.last_message_preview = truncate_preview(content)
    session_obj.updated_at = datetime.utcnow()
    await db_session.commit()


async def list_workspace_files(
    db_session: AsyncSession,
    *,
    session_id: str | None = None,
    scope: str | None = None,
) -> list[StoredFile]:
    query = select(StoredFile).order_by(StoredFile.created_at.desc())
    if session_id is not None:
        query = query.where(StoredFile.session_id == session_id)
    if scope is not None:
        query = query.where(StoredFile.scope == scope)
    return list((await db_session.scalars(query)).all())


async def find_matching_file(
    db_session: AsyncSession,
    *,
    session_id: str,
    content: str,
    attachment_ids: list[str],
) -> StoredFile | None:
    candidates = await list_workspace_files(db_session, session_id=session_id)
    if attachment_ids:
        preferred = [candidate for candidate in candidates if candidate.id in attachment_ids]
        if preferred:
            candidates = preferred

    lowered = content.lower()
    for candidate in candidates:
        if candidate.filename.lower() in lowered or candidate.title.lower() in lowered:
            return candidate

    return candidates[0] if candidates else None


async def run_python_tool(code: str) -> dict[str, Any]:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        code,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=PYTHON_TOOL_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        return {"stdout": "", "stderr": "Execution timed out.", "file_ids": []}

    return {
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stderr": stderr.decode("utf-8", errors="replace"),
        "file_ids": [],
    }


async def run_open_url_tool(urls: list[str]) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        for url in urls[:3]:
            try:
                response = await client.get(url)
                response.raise_for_status()
            except Exception:
                continue

            title = urlparse(url).netloc or url
            text = strip_html(response.text)[:2800]
            if not text:
                continue
            documents.append(
                {
                    "document_id": f"url:{url}",
                    "file_id": None,
                    "title": title,
                    "source": url,
                    "section": "Fetched URL",
                    "content": text,
                    "preview": text[:280],
                    "score": 1.0,
                }
            )
    return documents


async def build_prompt_messages(
    db_session: AsyncSession,
    *,
    session_id: str,
    current_user_content: str,
    prompt_documents: list[dict],
    python_result: dict[str, Any] | None,
    fetched_documents: list[dict] | None,
    read_result: dict[str, Any] | None,
) -> list[dict[str, str]]:
    history = list(
        (
            await db_session.scalars(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at.asc())
            )
        ).all()
    )[-MAX_HISTORY_MESSAGES:]

    prompt_messages: list[dict[str, str]] = []
    for message in history[:-1]:
        prompt_messages.append({"role": message.role, "content": message.content})

    additions: list[str] = [current_user_content.strip()]
    if prompt_documents:
        additions.append(
            "Here are workspace documents you can use. Cite them with [document].\n"
            + json.dumps({"documents": prompt_documents}, indent=2)
        )
    if read_result:
        additions.append(
            "File reader excerpt:\n"
            + json.dumps(
                {
                    "file_name": read_result["file_name"],
                    "start_char": read_result["start_char"],
                    "end_char": read_result["end_char"],
                    "content": read_result["content"],
                },
                indent=2,
            )
        )
    if fetched_documents:
        additions.append(
            "Fetched URL documents:\n"
            + json.dumps({"documents": fetched_documents}, indent=2)
        )
    if python_result:
        additions.append(
            "PYTHON_RESULT:\n"
            + json.dumps(python_result, indent=2)
        )

    prompt_messages.append({"role": "user", "content": "\n\n".join(additions)})
    return prompt_messages


async def stream_chat_packets(
    *,
    db_session: AsyncSession,
    runtime: BaseRuntime,
    retrieval_index: LocalRetrievalIndex,
    stop_event: asyncio.Event,
    request: ChatStreamRequest,
    model_settings: dict[str, Any],
) -> AsyncIterator[dict[str, Any]]:
    session_obj = await db_session.scalar(
        select(ChatSession).where(ChatSession.id == request.session_id)
    )
    if session_obj is None:
        raise HTTPException(status_code=404, detail="Session not found")

    last_message = await db_session.scalar(
        select(ChatMessage)
        .where(ChatMessage.session_id == request.session_id)
        .order_by(ChatMessage.created_at.desc())
    )
    parent_id = last_message.id if last_message else None

    user_message = ChatMessage(
        session_id=request.session_id,
        parent_message_id=parent_id,
        role="user",
        content=request.content.strip(),
        packets=[],
        documents=[],
        citations=[],
        meta={},
    )
    db_session.add(user_message)
    await db_session.flush()

    for attachment_id in request.attachment_ids:
        db_session.add(MessageFile(message_id=user_message.id, file_id=attachment_id))

    if session_obj.title == "New session":
        session_obj.title = build_session_title(request.content)
    session_obj.last_message_preview = truncate_preview(request.content)
    session_obj.updated_at = datetime.utcnow()
    await db_session.commit()
    await db_session.refresh(user_message)

    assistant_packets: list[dict[str, Any]] = []
    assistant_documents: list[dict[str, Any]] = []
    citation_records: list[dict[str, Any]] = []
    assistant_content = ""

    reasoning_packets = [
        packet("reasoning_start"),
        packet(
            "reasoning_delta",
            reasoning="Reviewing local context and choosing the right workspace tools.",
        ),
        packet("reasoning_done"),
        packet("section_end"),
    ]
    for item in reasoning_packets:
        assistant_packets.append(item)
        yield item

    session_files = await list_workspace_files(
        db_session,
        session_id=request.session_id,
    )
    library_files = await list_workspace_files(db_session, scope="library")
    allowed_file_ids = {file.id for file in [*session_files, *library_files]}

    search_documents: list[dict[str, Any]] = []
    if allowed_file_ids:
        queries = build_search_queries(request.content)
        search_documents = retrieval_index.search(
            query=queries[0],
            allowed_file_ids=allowed_file_ids,
        )
        tool_packets = [
            packet("search_tool_start", is_internet_search=False),
            packet("search_tool_queries_delta", queries=queries),
            packet("search_tool_documents_delta", documents=search_documents),
            packet("section_end"),
        ]
        for item in tool_packets:
            assistant_packets.append(item)
            yield item
        assistant_documents.extend(search_documents)

    read_result: dict[str, Any] | None = None
    if wants_file_reader(request.content):
        matched_file = await find_matching_file(
            db_session,
            session_id=request.session_id,
            content=request.content,
            attachment_ids=request.attachment_ids,
        )
        if matched_file is not None:
            read_result = read_file_excerpt(
                matched_file,
                start_char=0,
                num_chars=MAX_FILE_READ_CHARS,
            )
            tool_packets = [
                packet("file_reader_start"),
                packet("file_reader_result", **read_result),
                packet("section_end"),
            ]
            for item in tool_packets:
                assistant_packets.append(item)
                yield item
            assistant_documents.append(
                {
                    "document_id": f"file-reader:{matched_file.id}",
                    "file_id": matched_file.id,
                    "title": matched_file.title,
                    "source": matched_file.filename,
                    "section": "File Reader",
                    "content": read_result["content"],
                    "preview": read_result["preview"],
                    "score": 1.0,
                }
            )

    python_result: dict[str, Any] | None = None
    code = extract_python_code(request.content)
    if code:
        start_packet = packet("python_tool_start", code=code)
        assistant_packets.append(start_packet)
        yield start_packet
        python_result = await run_python_tool(code)
        result_packet = packet("python_tool_delta", **python_result)
        assistant_packets.append(result_packet)
        assistant_packets.append(packet("section_end"))
        yield result_packet
        yield packet("section_end")

    fetched_documents: list[dict[str, Any]] = []
    urls = URL_RE.findall(request.content)
    if urls:
        start_packet = packet("open_url_start")
        assistant_packets.append(start_packet)
        assistant_packets.append(packet("open_url_urls", urls=urls[:3]))
        yield start_packet
        yield packet("open_url_urls", urls=urls[:3])
        fetched_documents = await run_open_url_tool(urls)
        documents_packet = packet("open_url_documents", documents=fetched_documents)
        assistant_packets.append(documents_packet)
        assistant_packets.append(packet("section_end"))
        yield documents_packet
        yield packet("section_end")
        assistant_documents.extend(fetched_documents)

    prompt_documents, citation_map = build_prompt_documents(assistant_documents)
    messages = await build_prompt_messages(
        db_session,
        session_id=request.session_id,
        current_user_content=request.content,
        prompt_documents=prompt_documents,
        python_result=python_result,
        fetched_documents=fetched_documents or None,
        read_result=read_result,
    )

    message_start = packet(
        "message_start",
        id=f"assistant-{request.request_id}",
        content="",
        final_documents=assistant_documents,
    )
    assistant_packets.append(message_start)
    yield message_start

    seen_citations: set[int] = set()
    stop_reason = "finished"
    try:
        async for token in runtime.stream_chat(
            base_url=model_settings["ollama_base_url"],
            model=request.model or model_settings["default_chat_model"],
            system_prompt=build_system_prompt(datetime.now()),
            messages=messages,
            temperature=request.temperature
            if request.temperature is not None
            else model_settings["temperature"],
        ):
            if stop_event.is_set():
                stop_reason = "user_cancelled"
                break

            assistant_content += token
            delta_packet = packet("message_delta", content=token)
            assistant_packets.append(delta_packet)
            yield delta_packet

            for match in CITATION_RE.finditer(assistant_content):
                number = int(match.group(1))
                if number in seen_citations or number not in citation_map:
                    continue
                seen_citations.add(number)
                citation_packet = packet(
                    "citation_info",
                    citation_number=number,
                    document_id=citation_map[number],
                )
                citation_records.append(citation_packet)
                assistant_packets.append(citation_packet)
                yield citation_packet
    except asyncio.CancelledError:
        stop_reason = "user_cancelled"
    except Exception as exc:
        error_packet = packet("error", message=str(exc))
        assistant_packets.append(error_packet)
        yield error_packet
        stop_reason = "error"

    end_packet = packet("message_end")
    assistant_packets.append(end_packet)
    yield end_packet
    yield packet("section_end")
    stop_packet = packet("stop", stop_reason=stop_reason)
    assistant_packets.append(stop_packet)
    yield stop_packet

    assistant_message = ChatMessage(
        session_id=request.session_id,
        parent_message_id=user_message.id,
        role="assistant",
        content=assistant_content.strip(),
        model_name=request.model or model_settings["default_chat_model"],
        packets=assistant_packets,
        documents=assistant_documents,
        citations=citation_records,
        meta={"stop_reason": stop_reason},
    )
    db_session.add(assistant_message)
    session_obj.updated_at = datetime.utcnow()
    await db_session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    app.state.runtime = build_runtime()
    app.state.retrieval_index = LocalRetrievalIndex()
    app.state.stop_events = {}
    yield


app = FastAPI(title="mlaude-workspace", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": "mlaude-workspace", "status": "ok"}


@app.get("/api/health")
async def health(db_session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    settings = await load_model_settings(db_session)
    runtime: BaseRuntime = app.state.runtime
    status = await runtime.check(
        settings["ollama_base_url"],
        settings["default_chat_model"],
    )
    return {"runtime": status}


@app.get("/api/sessions")
async def list_sessions(
    q: str | None = None,
    db_session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    query = select(ChatSession).order_by(ChatSession.updated_at.desc())
    if q:
        needle = f"%{q.strip()}%"
        query = query.where(
            or_(
                ChatSession.title.ilike(needle),
                ChatSession.last_message_preview.ilike(needle),
            )
        )
    sessions = list((await db_session.scalars(query)).all())
    return [
        {
            "id": session.id,
            "title": session.title,
            "last_message_preview": session.last_message_preview,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "updated_at": session.updated_at.isoformat() if session.updated_at else None,
        }
        for session in sessions
    ]


@app.post("/api/sessions")
async def create_session(db_session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    session_obj = ChatSession(title="New session")
    db_session.add(session_obj)
    await db_session.commit()
    await db_session.refresh(session_obj)
    return {
        "id": session_obj.id,
        "title": session_obj.title,
        "last_message_preview": session_obj.last_message_preview,
        "created_at": session_obj.created_at.isoformat()
        if session_obj.created_at
        else None,
        "updated_at": session_obj.updated_at.isoformat()
        if session_obj.updated_at
        else None,
    }


@app.get("/api/sessions/{session_id}")
async def get_session_detail(
    session_id: str,
    db_session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    session_obj = await db_session.scalar(
        select(ChatSession).where(ChatSession.id == session_id)
    )
    if session_obj is None:
        raise HTTPException(status_code=404, detail="Session not found")

    files = await list_workspace_files(db_session, session_id=session_id)
    return {
        "session": {
            "id": session_obj.id,
            "title": session_obj.title,
            "last_message_preview": session_obj.last_message_preview,
            "created_at": session_obj.created_at.isoformat()
            if session_obj.created_at
            else None,
            "updated_at": session_obj.updated_at.isoformat()
            if session_obj.updated_at
            else None,
        },
        "messages": await serialize_messages(db_session, session_id),
        "files": [serialize_file(file_record) for file_record in files],
    }


@app.delete("/api/sessions/{session_id}")
async def delete_session(
    session_id: str,
    db_session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    session_obj = await db_session.scalar(
        select(ChatSession).where(ChatSession.id == session_id)
    )
    if session_obj is None:
        raise HTTPException(status_code=404, detail="Session not found")

    retrieval_index: LocalRetrievalIndex = app.state.retrieval_index
    files = await list_workspace_files(db_session, session_id=session_id)
    for file_record in files:
        retrieval_index.remove_file(file_record.id)
        directory = Path(file_record.storage_path).parent
        if directory.exists():
            for child in directory.iterdir():
                child.unlink(missing_ok=True)
            directory.rmdir()

    await db_session.execute(
        delete(MessageFile).where(
            MessageFile.message_id.in_(
                select(ChatMessage.id).where(ChatMessage.session_id == session_id)
            )
        )
    )
    await db_session.execute(delete(ChatMessage).where(ChatMessage.session_id == session_id))
    await db_session.execute(delete(StoredFile).where(StoredFile.session_id == session_id))
    await db_session.execute(delete(ChatSession).where(ChatSession.id == session_id))
    await db_session.commit()
    return {"ok": True}


@app.get("/api/files")
async def list_files(
    scope: str | None = None,
    session_id: str | None = None,
    db_session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    records = await list_workspace_files(
        db_session,
        session_id=session_id,
        scope=scope,
    )
    return [serialize_file(record) for record in records]


@app.post("/api/files/upload")
async def upload_file(
    file: UploadFile = File(...),
    scope: str = Form("chat"),
    session_id: str | None = Form(None),
    db_session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if scope not in {"chat", "library"}:
        raise HTTPException(status_code=400, detail="Invalid file scope")
    if scope == "chat" and not session_id:
        raise HTTPException(status_code=400, detail="session_id is required for chat files")

    retrieval_index: LocalRetrievalIndex = app.state.retrieval_index
    record = await save_upload(
        db_session=db_session,
        upload=file,
        scope=scope,
        session_id=session_id,
        retrieval_index=retrieval_index,
    )
    return serialize_file(record)


@app.get("/api/files/{file_id}/text")
async def get_file_text(
    file_id: str,
    start_char: int = 0,
    num_chars: int = MAX_FILE_READ_CHARS,
    db_session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    record = await get_file_or_404(db_session, file_id)
    return read_file_excerpt(record, start_char=start_char, num_chars=num_chars)


@app.get("/api/files/{file_id}/download")
async def download_file(
    file_id: str,
    db_session: AsyncSession = Depends(get_session),
) -> FileResponse:
    record = await get_file_or_404(db_session, file_id)
    return FileResponse(record.storage_path, filename=record.filename)


@app.get("/api/settings/model")
async def get_model_settings_endpoint(
    db_session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    settings = await load_model_settings(db_session)
    runtime: BaseRuntime = app.state.runtime
    models = await runtime.discover_models(settings["ollama_base_url"])
    health_status = await runtime.check(
        settings["ollama_base_url"],
        settings["default_chat_model"],
    )
    return {"settings": settings, "models": models, "health": health_status}


@app.get("/api/settings/model/discover")
async def discover_models_endpoint(
    base_url: str | None = None,
    db_session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    settings = await load_model_settings(db_session)
    runtime: BaseRuntime = app.state.runtime
    target_base_url = base_url or settings["ollama_base_url"]
    models = await runtime.discover_models(target_base_url)
    return {"models": models}


@app.put("/api/settings/model")
async def update_model_settings_endpoint(
    payload: ModelSettingsPayload,
    db_session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    value = await save_model_settings(db_session, payload)
    runtime: BaseRuntime = app.state.runtime
    health_status = await runtime.check(
        value["ollama_base_url"],
        value["default_chat_model"],
    )
    return {
        "settings": value,
        "models": health_status.get("models", []),
        "health": health_status,
    }


@app.post("/api/chat/stop/{request_id}")
async def stop_chat(request_id: str) -> dict[str, bool]:
    stop_events: dict[str, asyncio.Event] = app.state.stop_events
    event = stop_events.get(request_id)
    if event is not None:
        event.set()
    return {"ok": True}


@app.post("/api/chat/stream")
async def stream_chat(request: ChatStreamRequest) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        stop_events: dict[str, asyncio.Event] = app.state.stop_events
        stop_event = asyncio.Event()
        stop_events[request.request_id] = stop_event

        async with SessionLocal() as db_session:
            runtime: BaseRuntime = app.state.runtime
            retrieval_index: LocalRetrievalIndex = app.state.retrieval_index
            settings = await load_model_settings(db_session)

            try:
                async for item in stream_chat_packets(
                    db_session=db_session,
                    runtime=runtime,
                    retrieval_index=retrieval_index,
                    stop_event=stop_event,
                    request=request,
                    model_settings=settings,
                ):
                    yield json_line(item)
            finally:
                stop_events.pop(request.request_id, None)

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
