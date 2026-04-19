from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from mlaude.database import Base
from mlaude.models import AgentRun, ChatSession
from mlaude.server import finish_run_step, start_run_step, verify_citations


def test_verify_citations_accepts_grounded_and_rejects_invalid() -> None:
    assert verify_citations("The launch is delayed [1].", {1: "doc-1"})["ok"] is True
    rejected = verify_citations("The launch is delayed [2].", {1: "doc-1"})
    assert rejected["ok"] is False
    assert rejected["reason"] == "invalid_citation"


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
            output_payload={"mode": "web_only"},
        )
        assert step.status == "completed"
        assert step.output_payload["mode"] == "web_only"
        assert step.completed_at is not None

    await engine.dispose()
