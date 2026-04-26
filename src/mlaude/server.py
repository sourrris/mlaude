from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mlaude.browser_mcp import (
    BrowserGuardrailError,
    BrowserMCPError,
    BrowserMCPService,
    extract_urls,
)
from mlaude.database import SessionLocal, get_session, init_db
from mlaude.file_service import get_file_or_404, read_file_excerpt, save_upload, serialize_file
from mlaude.models import (
    AgentRun,
    AgentStep,
    AppSetting,
    ChatMessage,
    ChatSession,
    MessageFile,
    StoredFile,
)
from mlaude.retrieval import LocalRetrievalIndex
from mlaude.runtime import BaseRuntime, build_runtime
from mlaude.settings import (
    CORS_ORIGINS,
    DEFAULT_CHAT_MODEL,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_TEMPERATURE,
    MAX_FILE_READ_CHARS,
    MAX_HISTORY_MESSAGES,
    MAX_SEARCH_RESULTS,
    LLM_BASE_URL,
    PLAYWRIGHT_ENABLED,
)


CITATION_RE = re.compile(r"\[(\d+)\]")
CURRENT_INFO_RE = re.compile(
    r"\b(latest|today|current|recent|news|price|stock|weather|fresh|now|breaking)\b",
    re.IGNORECASE,
)
SIMPLE_CHAT_RE = re.compile(
    r"^\s*(hi|hello|hey|yo|sup|gm|gn|good morning|good afternoon|good evening|good night|thanks|thank you|how are you)\s*[!.?]*\s*$",
    re.IGNORECASE,
)
BASE_RUN_PLAN = [
    "classify",
    "retrieve_local",
]
FINAL_RUN_PLAN = ["rerank_evidence", "synthesize", "verify_citations"]
BROWSER_SEARCH_RE = re.compile(
    r"\b(search|google|look up|lookup|find online|web|internet|browse|latest|today|current|recent|news)\b",
    re.IGNORECASE,
)
BROWSER_CONTROL_RE = re.compile(
    r"\b(open|go to|navigate|click|type|fill|select|submit|screenshot|pdf|console|network|devtools|inspect)\b",
    re.IGNORECASE,
)


class ChatStreamRequest(BaseModel):
    request_id: str
    session_id: str
    content: str
    attachment_ids: list[str] = Field(default_factory=list)
    model: str | None = None
    temperature: float | None = None


class ModelSettingsPayload(BaseModel):
    provider: str = "lm-studio"
    llm_base_url: str = LLM_BASE_URL
    default_chat_model: str = DEFAULT_CHAT_MODEL
    default_embedding_model: str = DEFAULT_EMBEDDING_MODEL
    temperature: float = DEFAULT_TEMPERATURE


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def elapsed_ms(started_at: datetime | None, completed_at: datetime) -> int:
    start = as_utc_aware(started_at) if started_at else as_utc_aware(completed_at)
    end = as_utc_aware(completed_at)
    return max(0, int((end - start).total_seconds() * 1000))


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


def classify_browser_intent(content: str, *, freshness_sensitive: bool) -> str:
    lowered = content.lower()
    explicit_urls = extract_urls(content)
    if explicit_urls and BROWSER_CONTROL_RE.search(lowered):
        return "open_url"
    if BROWSER_CONTROL_RE.search(lowered) and (
        explicit_urls
        or "browser" in lowered
        or "page" in lowered
        or any(marker in lowered for marker in ("click", "type", "fill", "select", "screenshot", "pdf", "console", "network", "devtools"))
    ):
        return "browser_control"
    if explicit_urls:
        return "open_url"
    if freshness_sensitive or BROWSER_SEARCH_RE.search(lowered):
        return "web_search"
    return "none"


def build_dynamic_run_plan(classification: dict[str, Any]) -> list[str]:
    plan = ["classify"]
    if classification.get("has_local_files") and not classification.get("is_simple_chat"):
        plan.append("retrieve_local")

    browser_intent = classification.get("browser_intent")
    if browser_intent == "web_search":
        plan.append("browser_search")
    elif browser_intent in {"open_url", "browser_control"}:
        plan.append("browser_control")

    return [*plan, *FINAL_RUN_PLAN]


def build_system_prompt(now: datetime) -> str:
    return (
        "You are mlaude, a strict local-first research agent.\n\n"
        "Rules:\n"
        "- Use only the evidence documents provided in the prompt.\n"
        "- Every factual claim in the final answer must be cited with [n].\n"
        "- If the evidence set is too weak, say that evidence is insufficient.\n"
        "- Do not cite anything that is not in the evidence JSON.\n"
        "- For short greetings or social niceties, respond in one short sentence without deep analysis.\n"
        "- Keep the answer concise and directly responsive.\n\n"
        f"Current local date and time: {now.isoformat(timespec='minutes')}"
    )


def build_prompt_documents(documents: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[int, str]]:
    prompt_documents: list[dict[str, Any]] = []
    citation_map: dict[int, str] = {}

    for index, document in enumerate(documents, start=1):
        citation_map[index] = document["document_id"]
        prompt_documents.append(
            {
                "document": index,
                "title": document["title"],
                "source": document["source"],
                "source_kind": document.get("source_kind"),
                "section": document.get("section"),
                "contents": document["content"],
                "query": document.get("query"),
                "fetched_at": document.get("fetched_at"),
                "extract_status": document.get("extract_status"),
            }
        )

    return prompt_documents, citation_map


def build_prompt_messages(
    history: list[ChatMessage],
    *,
    current_user_content: str,
    prompt_documents: list[dict[str, Any]],
) -> list[dict[str, str]]:
    prompt_messages: list[dict[str, str]] = []
    for message in history[-MAX_HISTORY_MESSAGES:]:
        if message.role not in {"user", "assistant"} or not message.content.strip():
            continue
        prompt_messages.append({"role": message.role, "content": message.content})

    evidence_mode = bool(prompt_documents)
    if evidence_mode:
        user_prompt = (
            f"Question:\n{current_user_content.strip()}\n\n"
            "Evidence JSON:\n"
            + json.dumps({"documents": prompt_documents}, indent=2)
            + "\n\nRespond using only this evidence. Cite factual claims with [n]."
        )
    else:
        user_prompt = (
            f"Question:\n{current_user_content.strip()}\n\n"
            "No local evidence documents are available.\n"
            "If this is simple conversation or general help, answer directly.\n"
            "If the request needs grounded evidence, say that and ask for local files."
        )

    prompt_messages.append({"role": "user", "content": user_prompt})
    return prompt_messages


def classify_request(content: str, *, has_local_files: bool) -> dict[str, Any]:
    lowered = content.lower()
    current_info = bool(CURRENT_INFO_RE.search(lowered))
    explicit_urls = extract_urls(content)
    local_bias = has_local_files or "my file" in lowered or "uploaded" in lowered
    is_simple_chat = bool(SIMPLE_CHAT_RE.match(content.strip()))
    browser_intent = "none" if is_simple_chat else classify_browser_intent(
        content,
        freshness_sensitive=current_info,
    )

    if is_simple_chat:
        mode = "conversation"
    elif browser_intent in {"web_search", "open_url", "browser_control"} and local_bias:
        mode = "mixed"
    elif browser_intent in {"web_search", "open_url", "browser_control"}:
        mode = "web_only"
    elif local_bias:
        mode = "local_only"
    else:
        mode = "local_first"

    return {
        "mode": mode,
        "needs_web": browser_intent in {"web_search", "open_url", "browser_control"},
        "browser_intent": browser_intent,
        "explicit_urls": explicit_urls[:5],
        "playwright_enabled": PLAYWRIGHT_ENABLED,
        "freshness_sensitive": current_info,
        "has_local_files": has_local_files,
        "is_simple_chat": is_simple_chat,
    }


def should_enable_thinking(
    *,
    content: str,
    classification: dict[str, Any],
    evidence_count: int,
) -> bool:
    if classification.get("is_simple_chat"):
        return False
    if evidence_count > 0 or classification.get("freshness_sensitive"):
        return True

    lowered = content.lower()
    complex_intent_markers = (
        "analyze",
        "compare",
        "explain",
        "why",
        "how",
        "design",
        "debug",
        "implement",
        "step by step",
    )
    if any(marker in lowered for marker in complex_intent_markers):
        return True
    return len(content.strip()) > 100


def build_citation_packets(
    content: str,
    citation_map: dict[int, str],
) -> list[dict[str, Any]]:
    packets_out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for match in CITATION_RE.finditer(content):
        number = int(match.group(1))
        if number in seen or number not in citation_map:
            continue
        seen.add(number)
        packets_out.append(
            packet(
                "citation_info",
                citation_number=number,
                document_id=citation_map[number],
            )
        )
    return packets_out


def verify_citations(content: str, citation_map: dict[int, str]) -> dict[str, Any]:
    numbers = [int(match.group(1)) for match in CITATION_RE.finditer(content)]
    invalid = [number for number in numbers if number not in citation_map]
    if invalid:
        return {"ok": False, "reason": "invalid_citation", "invalid_numbers": invalid}

    if not citation_map:
        return {"ok": True, "reason": "no_evidence_mode", "invalid_numbers": []}

    if numbers:
        return {"ok": True, "reason": "verified", "invalid_numbers": []}

    lowered = content.lower()
    if "insufficient evidence" in lowered or "don't have enough" in lowered:
        return {"ok": True, "reason": "explicit_insufficient_evidence", "invalid_numbers": []}

    return {"ok": False, "reason": "missing_citations", "invalid_numbers": []}


async def load_model_settings(db_session: AsyncSession) -> dict[str, Any]:
    record = await db_session.scalar(
        select(AppSetting).where(AppSetting.key == "model_settings")
    )
    payload = {
        "provider": "lm-studio",
        "llm_base_url": LLM_BASE_URL,
        "default_chat_model": DEFAULT_CHAT_MODEL,
        "default_embedding_model": DEFAULT_EMBEDDING_MODEL,
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


def serialize_step(step: AgentStep) -> dict[str, Any]:
    return {
        "id": step.id,
        "run_id": step.run_id,
        "step_type": step.step_type,
        "order_index": step.order_index,
        "status": step.status,
        "input_payload": step.input_payload or {},
        "output_payload": step.output_payload or {},
        "error_text": step.error_text,
        "started_at": step.started_at.isoformat() if step.started_at else None,
        "completed_at": step.completed_at.isoformat() if step.completed_at else None,
    }


def serialize_run(run: AgentRun, steps: list[AgentStep]) -> dict[str, Any]:
    return {
        "id": run.id,
        "request_id": run.request_id,
        "session_id": run.session_id,
        "user_message_id": run.user_message_id,
        "assistant_message_id": run.assistant_message_id,
        "status": run.status,
        "stop_reason": run.stop_reason,
        "plan": run.plan or [],
        "timings": run.timings or {},
        "artifacts": run.artifacts or {},
        "meta": run.meta or {},
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "steps": [serialize_step(step) for step in steps],
    }


async def list_runs_for_session(
    db_session: AsyncSession,
    session_id: str,
) -> list[dict[str, Any]]:
    runs = list(
        (
            await db_session.scalars(
                select(AgentRun)
                .where(AgentRun.session_id == session_id)
                .order_by(AgentRun.created_at.desc())
            )
        ).all()
    )
    if not runs:
        return []

    steps = list(
        (
            await db_session.scalars(
                select(AgentStep)
                .where(AgentStep.run_id.in_([run.id for run in runs]))
                .order_by(AgentStep.order_index.asc(), AgentStep.started_at.asc())
            )
        ).all()
    )
    steps_by_run: dict[str, list[AgentStep]] = {}
    for step in steps:
        steps_by_run.setdefault(step.run_id, []).append(step)
    return [serialize_run(run, steps_by_run.get(run.id, [])) for run in runs]


async def start_run_step(
    db_session: AsyncSession,
    *,
    run: AgentRun,
    step_type: str,
    order_index: int,
    input_payload: dict[str, Any],
) -> AgentStep:
    step = AgentStep(
        run_id=run.id,
        step_type=step_type,
        order_index=order_index,
        status="running",
        input_payload=input_payload,
        output_payload={},
        started_at=utcnow(),
    )
    db_session.add(step)
    await db_session.commit()
    await db_session.refresh(step)
    return step


async def finish_run_step(
    db_session: AsyncSession,
    *,
    step: AgentStep,
    status: str,
    output_payload: dict[str, Any] | None = None,
    error_text: str | None = None,
) -> AgentStep:
    step.status = status
    step.output_payload = output_payload or {}
    step.error_text = error_text
    step.completed_at = utcnow()
    await db_session.commit()
    await db_session.refresh(step)
    return step


async def serialize_run_state(db_session: AsyncSession, run: AgentRun) -> dict[str, Any]:
    steps = list(
        (
            await db_session.scalars(
                select(AgentStep)
                .where(AgentStep.run_id == run.id)
                .order_by(AgentStep.order_index.asc(), AgentStep.started_at.asc())
            )
        ).all()
    )
    await db_session.refresh(run)
    return serialize_run(run, steps)


def stop_requested(stop_event: asyncio.Event) -> bool:
    return stop_event.is_set()


async def stream_chat_packets(
    *,
    db_session: AsyncSession,
    runtime: BaseRuntime,
    retrieval_index: LocalRetrievalIndex,
    browser_service: BrowserMCPService | None = None,
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
    session_obj.updated_at = utcnow()
    await db_session.commit()
    await db_session.refresh(user_message)

    session_files = await list_workspace_files(db_session, session_id=request.session_id)
    library_files = await list_workspace_files(db_session, scope="library")
    allowed_file_ids = {file.id for file in [*session_files, *library_files]}
    history = list(
        (
            await db_session.scalars(
                select(ChatMessage)
                .where(ChatMessage.session_id == request.session_id, ChatMessage.id != user_message.id)
                .order_by(ChatMessage.created_at.asc())
            )
        ).all()
    )
    classification = classify_request(
        request.content,
        has_local_files=bool(allowed_file_ids),
    )
    run_plan = build_dynamic_run_plan(classification)

    run = AgentRun(
        request_id=request.request_id,
        session_id=request.session_id,
        user_message_id=user_message.id,
        status="running",
        plan=run_plan,
        timings={},
        artifacts={},
        meta={
            "model": request.model or model_settings["default_chat_model"],
            "browser_intent": classification.get("browser_intent"),
        },
        started_at=utcnow(),
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    assistant_packets: list[dict[str, Any]] = []
    assistant_documents: list[dict[str, Any]] = []
    citation_records: list[dict[str, Any]] = []
    assistant_content = ""
    stop_reason = "finished"

    run_start_packet = packet("run_start", run=await serialize_run_state(db_session, run))
    assistant_packets.append(run_start_packet)
    yield run_start_packet

    local_documents: list[dict[str, Any]] = []
    browser_documents: list[dict[str, Any]] = []
    final_documents: list[dict[str, Any]] = []
    browser_direct_response: str | None = None
    captured_reasoning = ""
    message_started = False
    reasoning_started = False

    try:
        for order_index, step_type in enumerate(run_plan):
            if stop_requested(stop_event):
                stop_reason = "user_cancelled"
                break

            input_payload: dict[str, Any]
            if step_type == "classify":
                input_payload = {"content": request.content}
            elif step_type == "retrieve_local":
                input_payload = {
                    "query": request.content,
                    "allowed_file_count": len(allowed_file_ids),
                }
            elif step_type == "rerank_evidence":
                input_payload = {
                    "local_documents": len(local_documents),
                    "browser_documents": len(browser_documents),
                }
            elif step_type in {"browser_search", "browser_control"}:
                input_payload = {
                    "content": request.content,
                    "browser_intent": classification.get("browser_intent"),
                }
            elif step_type == "synthesize":
                input_payload = {"evidence_count": len(final_documents)}
            else:
                input_payload = {"answer_length": len(assistant_content)}

            step = await start_run_step(
                db_session,
                run=run,
                step_type=step_type,
                order_index=order_index,
                input_payload=input_payload,
            )
            step_start_packet = packet("step_start", run_id=run.id, step=serialize_step(step))
            assistant_packets.append(step_start_packet)
            yield step_start_packet

            if step_type == "classify":
                classification = classify_request(
                    request.content,
                    has_local_files=bool(allowed_file_ids),
                )
                step = await finish_run_step(
                    db_session,
                    step=step,
                    status="completed",
                    output_payload=classification,
                )
                run.artifacts = {**(run.artifacts or {}), "classification": classification}

            elif step_type == "retrieve_local":
                if classification.get("is_simple_chat"):
                    local_documents = []
                    step = await finish_run_step(
                        db_session,
                        step=step,
                        status="skipped",
                        output_payload={"documents_found": 0, "reason": "simple_chat"},
                    )
                elif allowed_file_ids:
                    local_documents = await retrieval_index.search(
                        query=request.content,
                        base_url=model_settings["llm_base_url"],
                        embedding_model=model_settings["default_embedding_model"],
                        allowed_file_ids=allowed_file_ids,
                        limit=MAX_SEARCH_RESULTS,
                    )
                    step = await finish_run_step(
                        db_session,
                        step=step,
                        status="completed",
                        output_payload={"documents_found": len(local_documents)},
                    )
                else:
                    local_documents = []
                    step = await finish_run_step(
                        db_session,
                        step=step,
                        status="completed",
                        output_payload={"documents_found": len(local_documents)},
                    )

                if local_documents:
                    tool_packets = [
                        packet("search_tool_start", is_internet_search=False),
                        packet("search_tool_queries_delta", queries=build_search_queries(request.content)),
                        packet("search_tool_documents_delta", documents=local_documents),
                        packet("section_end"),
                    ]
                    for item in tool_packets:
                        assistant_packets.append(item)
                        yield item
                    assistant_documents.extend(local_documents)

            elif step_type == "browser_search":
                if browser_service is None:
                    step = await finish_run_step(
                        db_session,
                        step=step,
                        status="error",
                        output_payload={"documents_found": 0},
                        error_text="Browser service is not available.",
                    )
                else:
                    try:
                        search_packets = [
                            packet("search_tool_start", is_internet_search=True),
                            packet("search_tool_queries_delta", queries=[request.content.strip()]),
                        ]
                        for item in search_packets:
                            assistant_packets.append(item)
                            yield item

                        result = await browser_service.search(
                            request.content.strip(),
                            max_results=min(MAX_SEARCH_RESULTS, 5),
                        )
                        browser_documents = result.documents
                        run.artifacts = {
                            **(run.artifacts or {}),
                            "browser_actions": result.packets,
                            "browser_documents": browser_documents,
                        }
                        for item in result.packets:
                            assistant_packets.append(item)
                            yield item
                        documents_packet = packet(
                            "search_tool_documents_delta",
                            documents=browser_documents,
                        )
                        assistant_packets.append(documents_packet)
                        yield documents_packet
                        section_end = packet("section_end")
                        assistant_packets.append(section_end)
                        yield section_end
                        assistant_documents.extend(browser_documents)
                        step = await finish_run_step(
                            db_session,
                            step=step,
                            status="completed",
                            output_payload={"documents_found": len(browser_documents)},
                        )
                    except BrowserMCPError as exc:
                        step = await finish_run_step(
                            db_session,
                            step=step,
                            status="error",
                            output_payload={"documents_found": 0},
                            error_text=str(exc),
                        )
                        browser_direct_response = str(exc)

            elif step_type == "browser_control":
                if browser_service is None:
                    step = await finish_run_step(
                        db_session,
                        step=step,
                        status="error",
                        output_payload={"actions": 0},
                        error_text="Browser service is not available.",
                    )
                else:
                    try:
                        if classification.get("browser_intent") == "open_url":
                            result = await browser_service.open_urls(
                                classification.get("explicit_urls") or [],
                                query=request.content.strip(),
                            )
                        else:
                            result = await browser_service.control(
                                user_request=request.content.strip(),
                                runtime=runtime,
                                model_settings=model_settings,
                                model=request.model or model_settings["default_chat_model"],
                                temperature=request.temperature
                                if request.temperature is not None
                                else model_settings["temperature"],
                            )
                        browser_documents = result.documents
                        browser_direct_response = result.final_response
                        run.artifacts = {
                            **(run.artifacts or {}),
                            "browser_actions": result.packets,
                            "browser_documents": browser_documents,
                            "browser_final_response": browser_direct_response,
                        }
                        for item in result.packets:
                            assistant_packets.append(item)
                            yield item
                        if browser_documents:
                            documents_packet = packet(
                                "search_tool_documents_delta",
                                documents=browser_documents,
                            )
                            assistant_packets.append(documents_packet)
                            yield documents_packet
                            assistant_documents.extend(browser_documents)
                        step = await finish_run_step(
                            db_session,
                            step=step,
                            status="completed",
                            output_payload={
                                "documents_found": len(browser_documents),
                                "final_response": bool(browser_direct_response),
                            },
                        )
                    except BrowserGuardrailError as exc:
                        browser_direct_response = str(exc)
                        step = await finish_run_step(
                            db_session,
                            step=step,
                            status="skipped",
                            output_payload={"guardrail": str(exc)},
                        )
                    except BrowserMCPError as exc:
                        browser_direct_response = str(exc)
                        step = await finish_run_step(
                            db_session,
                            step=step,
                            status="error",
                            output_payload={"documents_found": 0},
                            error_text=str(exc),
                        )

            elif step_type == "rerank_evidence":
                final_documents = await retrieval_index.rerank_evidence(
                    query=request.content,
                    documents=[*local_documents, *browser_documents],
                    base_url=model_settings["llm_base_url"],
                    embedding_model=model_settings["default_embedding_model"],
                    limit=MAX_SEARCH_RESULTS,
                )
                run.artifacts = {
                    **(run.artifacts or {}),
                    "evidence_pool": final_documents,
                }
                step = await finish_run_step(
                    db_session,
                    step=step,
                    status="completed" if final_documents else "skipped",
                    output_payload={"evidence_count": len(final_documents)},
                )

            elif step_type == "synthesize":
                prompt_documents, citation_map = build_prompt_documents(final_documents)
                messages = build_prompt_messages(
                    history,
                    current_user_content=request.content,
                    prompt_documents=prompt_documents,
                )
                if not message_started:
                    message_start = packet(
                        "message_start",
                        id=f"assistant-{request.request_id}",
                        content="",
                        final_documents=final_documents,
                    )
                    assistant_packets.append(message_start)
                    yield message_start
                    message_started = True

                if browser_direct_response and not final_documents:
                    assistant_content = browser_direct_response
                    for char in assistant_content:
                        delta_packet = packet("message_delta", content=char)
                        assistant_packets.append(delta_packet)
                        yield delta_packet
                else:
                    async for chunk in runtime.stream_chat(
                        base_url=model_settings["llm_base_url"],
                        model=request.model or model_settings["default_chat_model"],
                        system_prompt=build_system_prompt(utcnow()),
                        messages=messages,
                        temperature=request.temperature
                        if request.temperature is not None
                        else model_settings["temperature"],
                        think=should_enable_thinking(
                            content=request.content,
                            classification=classification,
                            evidence_count=len(final_documents),
                        ),
                    ):
                        if stop_requested(stop_event):
                            stop_reason = "user_cancelled"
                            break

                        thinking = chunk.get("thinking", "")
                        if thinking:
                            captured_reasoning += thinking
                            if not reasoning_started:
                                reasoning_start_packet = packet("reasoning_start")
                                assistant_packets.append(reasoning_start_packet)
                                yield reasoning_start_packet
                                reasoning_started = True
                            for char in thinking:
                                reasoning_delta_packet = packet("reasoning_delta", reasoning=char)
                                assistant_packets.append(reasoning_delta_packet)
                                yield reasoning_delta_packet

                        content = chunk.get("content", "")
                        if content:
                            assistant_content += content
                            for char in content:
                                delta_packet = packet("message_delta", content=char)
                                assistant_packets.append(delta_packet)
                                yield delta_packet

                if reasoning_started:
                    reasoning_done_packet = packet("reasoning_done")
                    reasoning_section_end_packet = packet("section_end")
                    assistant_packets.append(reasoning_done_packet)
                    assistant_packets.append(reasoning_section_end_packet)
                    yield reasoning_done_packet
                    yield reasoning_section_end_packet
                    reasoning_started = False

                step = await finish_run_step(
                    db_session,
                    step=step,
                    status="completed" if assistant_content else "skipped",
                    output_payload={"answer_length": len(assistant_content)},
                )

            elif step_type == "verify_citations":
                prompt_documents, citation_map = build_prompt_documents(final_documents)
                verification = verify_citations(assistant_content, citation_map)
                run.artifacts = {
                    **(run.artifacts or {}),
                    "verification": verification,
                    "answer_preview": assistant_content[:400],
                }
                if not assistant_content:
                    step = await finish_run_step(
                        db_session,
                        step=step,
                        status="skipped",
                        output_payload=verification,
                    )
                elif verification["ok"]:
                    step = await finish_run_step(
                        db_session,
                        step=step,
                        status="completed",
                        output_payload=verification,
                    )
                else:
                    assistant_content = (
                        "I don't have enough verified evidence to answer that confidently "
                        "from the current local sources."
                    )
                    stop_reason = "insufficient_evidence"
                    step = await finish_run_step(
                        db_session,
                        step=step,
                        status="error",
                        output_payload=verification,
                        error_text=verification["reason"],
                    )

            await db_session.commit()
            step_result_packet = packet(
                "step_result",
                run_id=run.id,
                step=serialize_step(step),
            )
            assistant_packets.append(step_result_packet)
            yield step_result_packet

        prompt_documents, citation_map = build_prompt_documents(final_documents)
        if assistant_content or stop_reason in {"insufficient_evidence", "user_cancelled"}:
            if not message_started:
                message_start = packet(
                    "message_start",
                    id=f"assistant-{request.request_id}",
                    content="",
                    final_documents=final_documents,
                )
                assistant_packets.append(message_start)
                yield message_start
                message_started = True

                if captured_reasoning:
                    reasoning_packets = [
                        packet("reasoning_start"),
                        packet("reasoning_delta", reasoning=captured_reasoning),
                        packet("reasoning_done"),
                        packet("section_end"),
                    ]
                    for item in reasoning_packets:
                        assistant_packets.append(item)
                        yield item

                for char in assistant_content:
                    delta_packet = packet("message_delta", content=char)
                    assistant_packets.append(delta_packet)
                    yield delta_packet

            citation_records = build_citation_packets(assistant_content, citation_map)
            for item in citation_records:
                assistant_packets.append(item)
                yield item

            end_packet = packet("message_end")
            assistant_packets.append(end_packet)
            assistant_packets.append(packet("section_end"))
            yield end_packet
            yield packet("section_end")

        if stop_reason == "finished" and not assistant_content:
            stop_reason = "insufficient_evidence"

        run.status = "completed" if stop_reason == "finished" else "stopped"
        run.stop_reason = stop_reason
        run.completed_at = utcnow()
        run.timings = {
            **(run.timings or {}),
            "total_ms": elapsed_ms(run.started_at, run.completed_at),
        }

        assistant_message = ChatMessage(
            session_id=request.session_id,
            parent_message_id=user_message.id,
            role="assistant",
            content=assistant_content.strip(),
            model_name=request.model or model_settings["default_chat_model"],
            packets=assistant_packets,
            documents=final_documents,
            citations=citation_records,
            meta={"stop_reason": stop_reason, "run_id": run.id},
        )
        db_session.add(assistant_message)
        await db_session.flush()
        run.assistant_message_id = assistant_message.id
        session_obj.updated_at = utcnow()
        await db_session.commit()

        run_complete_packet = packet("run_complete", run=await serialize_run_state(db_session, run))
        assistant_packets.append(run_complete_packet)
        yield run_complete_packet

        stop_packet = packet("stop", stop_reason=stop_reason)
        assistant_packets.append(stop_packet)
        yield stop_packet

        assistant_message.packets = assistant_packets
        await db_session.commit()

    except asyncio.CancelledError:
        run.status = "stopped"
        run.stop_reason = "user_cancelled"
        run.completed_at = utcnow()
        await db_session.commit()
        raise
    except Exception as exc:
        run.status = "error"
        run.stop_reason = "error"
        run.completed_at = utcnow()
        run.artifacts = {**(run.artifacts or {}), "error": str(exc)}
        await db_session.commit()
        error_packet = packet("run_error", run_id=run.id, message=str(exc))
        assistant_packets.append(error_packet)
        yield error_packet
        yield packet("error", message=str(exc))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    app.state.runtime = build_runtime()
    app.state.retrieval_index = LocalRetrievalIndex()
    app.state.browser_service = BrowserMCPService()
    app.state.stop_events = {}
    try:
        yield
    finally:
        await app.state.browser_service.close()


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
    runtime: BaseRuntime = build_runtime(settings["provider"])
    status = await runtime.check(
        settings["llm_base_url"],
        settings["default_chat_model"],
    )
    models = status.get("models", [])
    status["embedding_model_available"] = settings["default_embedding_model"] in models
    status["default_embedding_model"] = settings["default_embedding_model"]
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
        "runs": await list_runs_for_session(db_session, session_id),
    }


@app.get("/api/sessions/{session_id}/runs")
async def get_session_runs(
    session_id: str,
    db_session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    return await list_runs_for_session(db_session, session_id)


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
    await db_session.execute(delete(AgentStep).where(AgentStep.run_id.in_(select(AgentRun.id).where(AgentRun.session_id == session_id))))
    await db_session.execute(delete(AgentRun).where(AgentRun.session_id == session_id))
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
    settings = await load_model_settings(db_session)
    record = await save_upload(
        db_session=db_session,
        upload=file,
        scope=scope,
        session_id=session_id,
        retrieval_index=retrieval_index,
        llm_base_url=settings["llm_base_url"],
        embedding_model=settings["default_embedding_model"],
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
    runtime: BaseRuntime = build_runtime(settings["provider"])
    health_status = await runtime.check(
        settings["llm_base_url"],
        settings["default_chat_model"],
    )
    models = health_status.get("models", [])
    health_status["embedding_model_available"] = settings["default_embedding_model"] in models
    health_status["default_embedding_model"] = settings["default_embedding_model"]
    return {"settings": settings, "models": models, "health": health_status}


@app.get("/api/settings/model/discover")
async def discover_models_endpoint(
    base_url: str | None = None,
    db_session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    settings = await load_model_settings(db_session)
    runtime: BaseRuntime = build_runtime(settings["provider"])
    target_base_url = base_url or settings["llm_base_url"]
    try:
        models = await runtime.discover_models(target_base_url)
    except Exception:
        models = []
    return {"models": models}


@app.put("/api/settings/model")
async def update_model_settings_endpoint(
    payload: ModelSettingsPayload,
    db_session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    value = await save_model_settings(db_session, payload)
    runtime: BaseRuntime = build_runtime(value["provider"])
    health_status = await runtime.check(
        value["llm_base_url"],
        value["default_chat_model"],
    )
    models = health_status.get("models", [])
    health_status["embedding_model_available"] = value["default_embedding_model"] in models
    health_status["default_embedding_model"] = value["default_embedding_model"]
    return {
        "settings": value,
        "models": models,
        "health": health_status,
    }


@app.post("/api/models/load")
async def load_model_endpoint(
    model: str,
    db_session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    settings = await load_model_settings(db_session)
    runtime: BaseRuntime = build_runtime(settings["provider"])
    return await runtime.load_model(settings["llm_base_url"], model)


@app.post("/api/models/download")
async def download_model_endpoint(
    model: str,
    db_session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    settings = await load_model_settings(db_session)
    runtime: BaseRuntime = build_runtime(settings["provider"])
    return await runtime.download_model(settings["llm_base_url"], model)


@app.get("/api/models/download/{job_id}")
async def get_download_status_endpoint(
    job_id: str,
    db_session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    settings = await load_model_settings(db_session)
    runtime: BaseRuntime = build_runtime(settings["provider"])
    return await runtime.get_download_status(settings["llm_base_url"], job_id)


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
            settings = await load_model_settings(db_session)
            runtime: BaseRuntime = build_runtime(settings["provider"])
            retrieval_index: LocalRetrievalIndex = app.state.retrieval_index
            browser_service: BrowserMCPService = app.state.browser_service

            try:
                async for item in stream_chat_packets(
                    db_session=db_session,
                    runtime=runtime,
                    retrieval_index=retrieval_index,
                    browser_service=browser_service,
                    stop_event=stop_event,
                    request=request,
                    model_settings=settings,
                ):
                    yield json_line(item)
            finally:
                stop_events.pop(request.request_id, None)

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
