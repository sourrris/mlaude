from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from mlaude.database import Base
from mlaude.browser_mcp import BrowserSearchResult
from mlaude.models import AgentRun, ChatSession
from mlaude.runtime import MockRuntime
from mlaude.server import (
    ChatStreamRequest,
    build_dynamic_run_plan,
    build_prompt_messages,
    classify_request,
    elapsed_ms,
    finish_run_step,
    should_enable_thinking,
    start_run_step,
    stream_chat_packets,
    verify_citations,
)


def test_verify_citations_accepts_grounded_and_rejects_invalid() -> None:
    assert verify_citations("The launch is delayed [1].", {1: "doc-1"})["ok"] is True
    rejected = verify_citations("The launch is delayed [2].", {1: "doc-1"})
    assert rejected["ok"] is False
    assert rejected["reason"] == "invalid_citation"


def test_verify_citations_allows_no_evidence_mode() -> None:
    accepted = verify_citations("hi there", {})
    assert accepted["ok"] is True
    assert accepted["reason"] == "no_evidence_mode"


def test_build_prompt_messages_without_evidence_allows_direct_answer() -> None:
    messages = build_prompt_messages(
        [],
        current_user_content="hi",
        prompt_documents=[],
    )
    assert len(messages) == 1
    content = messages[0]["content"].lower()
    assert "no local evidence documents are available" in content
    assert "answer directly" in content


def test_classify_request_marks_simple_chat_as_conversation() -> None:
    classification = classify_request("hi", has_local_files=False)
    assert classification["mode"] == "conversation"
    assert classification["needs_web"] is False
    assert classification["is_simple_chat"] is True


def test_classify_request_marks_fresh_question_for_browser_search() -> None:
    classification = classify_request("What are the latest Playwright MCP docs?", has_local_files=False)
    assert classification["needs_web"] is True
    assert classification["browser_intent"] == "web_search"
    assert classification["mode"] == "web_only"


def test_classify_request_marks_url_open_and_browser_control() -> None:
    open_url = classify_request("Open https://example.com and summarize it", has_local_files=False)
    assert open_url["browser_intent"] == "open_url"
    assert open_url["explicit_urls"] == ["https://example.com"]

    control = classify_request("Click the pricing tab in the browser", has_local_files=False)
    assert control["browser_intent"] == "browser_control"


def test_dynamic_plan_adds_browser_steps_only_when_needed() -> None:
    search_classification = classify_request("search Google for Playwright MCP", has_local_files=True)
    assert build_dynamic_run_plan(search_classification) == [
        "classify",
        "retrieve_local",
        "browser_search",
        "rerank_evidence",
        "synthesize",
        "verify_citations",
    ]

    simple_classification = classify_request("hi", has_local_files=False)
    assert build_dynamic_run_plan(simple_classification) == [
        "classify",
        "rerank_evidence",
        "synthesize",
        "verify_citations",
    ]


def test_should_enable_thinking_for_simple_chat_is_false() -> None:
    classification = {"is_simple_chat": True, "freshness_sensitive": False}
    assert (
        should_enable_thinking(
            content="hello",
            classification=classification,
            evidence_count=0,
        )
        is False
    )


def test_should_enable_thinking_for_complex_request_is_true() -> None:
    classification = {"is_simple_chat": False, "freshness_sensitive": False}
    assert (
        should_enable_thinking(
            content="Explain how to debug this runtime error step by step.",
            classification=classification,
            evidence_count=0,
        )
        is True
    )


def test_elapsed_ms_handles_mixed_timezone_datetimes() -> None:
    started_naive = datetime(2026, 1, 2, 3, 4, 5)
    completed_aware = datetime(2026, 1, 2, 3, 4, 7, tzinfo=UTC)
    assert elapsed_ms(started_naive, completed_aware) == 2000


@pytest.mark.asyncio
async def test_run_step_transitions_persist() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_maker() as session:
        chat_session = ChatSession(title="Run Test")
        session.add(chat_session)
        await session.commit()
        await session.refresh(chat_session)

        run = AgentRun(
            request_id="req-1",
            session_id=chat_session.id,
            status="running",
            plan=["classify"],
            timings={},
            artifacts={},
            meta={},
            started_at=datetime.now(UTC),
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)

        step = await start_run_step(
            session,
            run=run,
            step_type="classify",
            order_index=0,
            input_payload={"content": "latest launch window"},
        )
        assert step.status == "running"
        assert step.input_payload["content"] == "latest launch window"

        step = await finish_run_step(
            session,
            step=step,
            status="completed",
            output_payload={"mode": "local_first"},
        )
        assert step.status == "completed"
        assert step.output_payload["mode"] == "local_first"
        assert step.completed_at is not None

    await engine.dispose()


class FakeRetrievalIndex:
    async def search(self, **kwargs):  # noqa: ANN003, ANN201
        return []

    async def rerank_evidence(self, *, documents, limit, **kwargs):  # noqa: ANN001, ANN003, ANN201
        return documents[:limit]


class FakeBrowserService:
    async def search(self, query: str, *, max_results: int) -> BrowserSearchResult:  # noqa: ARG002
        document = {
            "document_id": "browser:doc-1",
            "file_id": None,
            "title": "Playwright MCP",
            "source": "https://playwright.dev/mcp/",
            "source_kind": "web_page",
            "section": "Browser",
            "content": "Playwright MCP lets agents control a browser.",
            "preview": "Playwright MCP lets agents control a browser.",
            "query": query,
            "score": 1,
            "retrieval_score": 1,
            "fetched_at": "2026-01-01T00:00:00+00:00",
            "extract_status": "complete",
        }
        return BrowserSearchResult(
            documents=[document],
            packets=[
                {
                    "type": "browser_tool_start",
                    "tool": "browser_navigate",
                    "summary": "Opening Google",
                },
                {
                    "type": "browser_tool_result",
                    "tool": "browser_navigate",
                    "status": "completed",
                    "summary": "Read result",
                    "url": document["source"],
                    "title": document["title"],
                },
            ],
        )


@pytest.mark.asyncio
async def test_stream_chat_packets_emits_browser_search_packets_and_persists_run() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_maker() as session:
        chat_session = ChatSession(title="Browser Test")
        session.add(chat_session)
        await session.commit()
        await session.refresh(chat_session)

        packets = [
            packet
            async for packet in stream_chat_packets(
                db_session=session,
                runtime=MockRuntime(),
                retrieval_index=FakeRetrievalIndex(),  # type: ignore[arg-type]
                browser_service=FakeBrowserService(),  # type: ignore[arg-type]
                stop_event=asyncio.Event(),
                request=ChatStreamRequest(
                    request_id="req-browser",
                    session_id=chat_session.id,
                    content="search Google for Playwright MCP docs",
                    attachment_ids=[],
                    model="mock-chat:latest",
                    temperature=0.2,
                ),
                model_settings={
                    "provider": "lm-studio",
                    "llm_base_url": "http://127.0.0.1:1234",
                    "default_chat_model": "mock-chat:latest",
                    "default_embedding_model": "",
                    "temperature": 0.2,
                },
            )
        ]

        assert any(
            packet["type"] == "search_tool_start" and packet.get("is_internet_search") is True
            for packet in packets
        )
        assert any(packet["type"] == "browser_tool_start" for packet in packets)
        assert any(packet["type"] == "citation_info" for packet in packets)

        run = await session.scalar(
            select(AgentRun).where(AgentRun.request_id == "req-browser")
        )
        assert run is not None
        assert "browser_search" in run.plan
        assert run.artifacts["browser_documents"][0]["source_kind"] == "web_page"

    await engine.dispose()
