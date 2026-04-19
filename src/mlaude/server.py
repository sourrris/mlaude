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
    MAX_WEB_FETCH_RESULTS,
    MAX_WEB_SEARCH_RESULTS,
    OLLAMA_BASE_URL,
)
from mlaude.tools.web_search import fetch_pages, page_to_document, search_web


CITATION_RE = re.compile(r"\[(\d+)\]")
CURRENT_INFO_RE = re.compile(
    r"\b(latest|today|current|recent|news|price|stock|weather|fresh|now|breaking)\b",
    re.IGNORECASE,
)
FIXED_RUN_PLAN = [
    "classify",
    "retrieve_local",
    "plan_search",
    "search_web",
    "fetch_page",
    "extract_page",
    "rerank_evidence",
    "synthesize",
    "verify_citations",
]


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
    default_embedding_model: str = DEFAULT_EMBEDDING_MODEL
    temperature: float = DEFAULT_TEMPERATURE


def utcnow() -> datetime:
    return datetime.now(UTC)


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


def build_system_prompt(now: datetime) -> str:
    return (
        "You are mlaude, a strict local-first research agent.\n\n"
        "Rules:\n"
        "- Use only the evidence documents provided in the prompt.\n"
        "- Every factual claim in the final answer must be cited with [n].\n"
        "- If the evidence set is too weak, say that evidence is insufficient.\n"
        "- Do not cite anything that is not in the evidence JSON.\n"
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

    prompt_messages.append(
        {
            "role": "user",
            "content": (
                f"Question:\n{current_user_content.strip()}\n\n"
                "Evidence JSON:\n"
                + json.dumps({"documents": prompt_documents}, indent=2)
                + "\n\nRespond using only this evidence."
            ),
        }
    )
    return prompt_messages


def classify_request(content: str, *, has_local_files: bool) -> dict[str, Any]:
    lowered = content.lower()
    current_info = bool(CURRENT_INFO_RE.search(lowered))
    explicit_urls = re.findall(r"https?://[^\s]+", content)
    local_bias = has_local_files or "my file" in lowered or "uploaded" in lowered

    if explicit_urls:
        mode = "mixed" if local_bias else "web_only"
    elif current_info and local_bias:
        mode = "mixed"
    elif current_info:
        mode = "web_only"
    elif local_bias:
        mode = "local_only"
    else:
        mode = "local_first"

    return {
        "mode": mode,
        "needs_web": mode in {"mixed", "web_only"},
        "explicit_urls": explicit_urls[:MAX_WEB_FETCH_RESULTS],
        "freshness_sensitive": current_info,
        "has_local_files": has_local_files,
    }


def chunk_text_for_stream(text: str, chunk_size: int = 180) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > chunk_size and current:
            chunks.append(f"{current} ")
            current = word
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


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
        "ollama_base_url": OLLAMA_BASE_URL,
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


async def collect_model_response(
    *,
    runtime: BaseRuntime,
    model_settings: dict[str, Any],
    request: ChatStreamRequest,
    messages: list[dict[str, str]],
    stop_event: asyncio.Event,
) -> tuple[str, str, str]:
    answer_parts: list[str] = []
    reasoning_parts: list[str] = []
    stop_reason = "finished"

    async for chunk in runtime.stream_chat(
        base_url=model_settings["ollama_base_url"],
        model=request.model or model_settings["default_chat_model"],
        system_prompt=build_system_prompt(utcnow()),
        messages=messages,
        temperature=request.temperature
        if request.temperature is not None
        else model_settings["temperature"],
    ):
        if stop_requested(stop_event):
            stop_reason = "user_cancelled"
            break
        if chunk.get("thinking"):
            reasoning_parts.append(chunk["thinking"])
        if chunk.get("content"):
            answer_parts.append(chunk["content"])

    return "".join(answer_parts).strip(), "".join(reasoning_parts).strip(), stop_reason


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
    session_obj.updated_at = utcnow()
    await db_session.commit()
    await db_session.refresh(user_message)

    run = AgentRun(
        request_id=request.request_id,
        session_id=request.session_id,
        user_message_id=user_message.id,
        status="running",
        plan=FIXED_RUN_PLAN,
        timings={},
        artifacts={},
        meta={"model": request.model or model_settings["default_chat_model"]},
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

    classification: dict[str, Any] = {}
    local_documents: list[dict[str, Any]] = []
    search_queries: list[str] = []
    web_results: list[dict[str, Any]] = []
    fetched_pages: list[dict[str, Any]] = []
    extracted_pages: list[dict[str, Any]] = []
    final_documents: list[dict[str, Any]] = []
    captured_reasoning = ""

    try:
        for order_index, step_type in enumerate(FIXED_RUN_PLAN):
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
            elif step_type == "plan_search":
                input_payload = {"content": request.content, "classification": classification}
            elif step_type == "search_web":
                input_payload = {"queries": search_queries}
            elif step_type == "fetch_page":
                input_payload = {
                    "urls": [item["source"] for item in web_results[:MAX_WEB_FETCH_RESULTS]]
                    or classification.get("explicit_urls", []),
                }
            elif step_type == "extract_page":
                input_payload = {"pages": len(fetched_pages)}
            elif step_type == "rerank_evidence":
                input_payload = {
                    "local_documents": len(local_documents),
                    "web_documents": len(extracted_pages),
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
                if allowed_file_ids:
                    local_documents = await retrieval_index.search(
                        query=request.content,
                        base_url=model_settings["ollama_base_url"],
                        embedding_model=model_settings["default_embedding_model"],
                        allowed_file_ids=allowed_file_ids,
                        limit=MAX_SEARCH_RESULTS,
                    )
                else:
                    local_documents = []

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

                step = await finish_run_step(
                    db_session,
                    step=step,
                    status="completed",
                    output_payload={"documents_found": len(local_documents)},
                )

            elif step_type == "plan_search":
                needs_web = classification.get("needs_web", False)
                if not needs_web and not local_documents:
                    needs_web = True
                search_queries = (
                    classification.get("explicit_urls", [])
                    if classification.get("explicit_urls")
                    else build_search_queries(request.content)
                )
                planned = {
                    "needs_web": needs_web,
                    "queries": search_queries if needs_web else [],
                }
                step = await finish_run_step(
                    db_session,
                    step=step,
                    status="completed" if needs_web else "skipped",
                    output_payload=planned,
                )
                run.artifacts = {**(run.artifacts or {}), "search_plan": planned}
                if not needs_web:
                    search_queries = []

            elif step_type == "search_web":
                if not search_queries:
                    step = await finish_run_step(
                        db_session,
                        step=step,
                        status="skipped",
                        output_payload={"documents_found": 0},
                    )
                else:
                    if classification.get("explicit_urls"):
                        web_results = [
                            {
                                "document_id": f"web-result:explicit:{url}",
                                "file_id": None,
                                "title": url,
                                "source": url,
                                "source_kind": "web_result",
                                "section": "Explicit URL",
                                "content": "",
                                "preview": url,
                                "query": request.content,
                                "score": 1.0,
                                "retrieval_score": 1.0,
                                "fetched_at": utcnow().isoformat(),
                                "extract_status": "not_fetched",
                            }
                            for url in classification["explicit_urls"]
                        ]
                    else:
                        web_results = await search_web(
                            search_queries[0],
                            max_results=MAX_WEB_SEARCH_RESULTS,
                        )
                    if web_results:
                        tool_packets = [
                            packet("search_tool_start", is_internet_search=True),
                            packet("search_tool_queries_delta", queries=search_queries),
                            packet("search_tool_documents_delta", documents=web_results),
                            packet("section_end"),
                        ]
                        for item in tool_packets:
                            assistant_packets.append(item)
                            yield item
                    assistant_documents.extend(web_results)
                    step = await finish_run_step(
                        db_session,
                        step=step,
                        status="completed",
                        output_payload={"documents_found": len(web_results)},
                    )

            elif step_type == "fetch_page":
                urls = (
                    classification.get("explicit_urls", [])
                    or [item["source"] for item in web_results[:MAX_WEB_FETCH_RESULTS]]
                )
                if not urls:
                    step = await finish_run_step(
                        db_session,
                        step=step,
                        status="skipped",
                        output_payload={"pages_fetched": 0},
                    )
                else:
                    fetched_pages = await fetch_pages(urls[:MAX_WEB_FETCH_RESULTS])
                    step = await finish_run_step(
                        db_session,
                        step=step,
                        status="completed",
                        output_payload={
                            "pages_fetched": len(fetched_pages),
                            "failed": sum(1 for page in fetched_pages if page.get("error")),
                        },
                    )

            elif step_type == "extract_page":
                if not fetched_pages:
                    step = await finish_run_step(
                        db_session,
                        step=step,
                        status="skipped",
                        output_payload={"documents_extracted": 0},
                    )
                else:
                    extracted_pages = [
                        page_to_document(page=page, query=request.content, rank=index)
                        for index, page in enumerate(fetched_pages, start=1)
                        if page.get("html")
                    ]
                    assistant_documents.extend(extracted_pages)
                    step = await finish_run_step(
                        db_session,
                        step=step,
                        status="completed",
                        output_payload={"documents_extracted": len(extracted_pages)},
                    )

            elif step_type == "rerank_evidence":
                final_documents = await retrieval_index.rerank_evidence(
                    query=request.content,
                    documents=[*local_documents, *extracted_pages],
                    base_url=model_settings["ollama_base_url"],
                    embedding_model=model_settings["default_embedding_model"],
                    limit=MAX_SEARCH_RESULTS,
                )
                run.artifacts = {
                    **(run.artifacts or {}),
                    "evidence_pool": final_documents,
                    "search_queries": search_queries,
                }
                step = await finish_run_step(
                    db_session,
                    step=step,
                    status="completed" if final_documents else "skipped",
                    output_payload={"evidence_count": len(final_documents)},
                )

            elif step_type == "synthesize":
                if not final_documents:
                    assistant_content = (
                        "I don't have enough grounded evidence to answer that confidently. "
                        "Try adding local files or letting the run fetch stronger web sources."
                    )
                    stop_reason = "insufficient_evidence"
                    step = await finish_run_step(
                        db_session,
                        step=step,
                        status="skipped",
                        output_payload={"answer_length": 0},
                    )
                    continue

                prompt_documents, citation_map = build_prompt_documents(final_documents)
                messages = build_prompt_messages(
                    history,
                    current_user_content=request.content,
                    prompt_documents=prompt_documents,
                )
                assistant_content, captured_reasoning, synth_stop_reason = await collect_model_response(
                    runtime=runtime,
                    model_settings=model_settings,
                    request=request,
                    messages=messages,
                    stop_event=stop_event,
                )
                if synth_stop_reason != "finished":
                    stop_reason = synth_stop_reason
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
                        "from the current local and fetched sources."
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
            message_start = packet(
                "message_start",
                id=f"assistant-{request.request_id}",
                content="",
                final_documents=final_documents,
            )
            assistant_packets.append(message_start)
            yield message_start

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

            for chunk in chunk_text_for_stream(assistant_content):
                delta_packet = packet("message_delta", content=chunk)
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
            "total_ms": int((run.completed_at - (run.started_at or run.completed_at)).total_seconds() * 1000),
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
        ollama_base_url=settings["ollama_base_url"],
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
    runtime: BaseRuntime = app.state.runtime
    health_status = await runtime.check(
        settings["ollama_base_url"],
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
    runtime: BaseRuntime = app.state.runtime
    target_base_url = base_url or settings["ollama_base_url"]
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
    runtime: BaseRuntime = app.state.runtime
    health_status = await runtime.check(
        value["ollama_base_url"],
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
