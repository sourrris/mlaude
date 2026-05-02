from __future__ import annotations

import json
import tempfile
from pathlib import Path

from mlaude.commands import COMMANDS, resolve_command
from mlaude.safety import SafetyPolicy
from mlaude.state import SessionDB
from mlaude.tools.registry import ToolRegistry


def test_command_surface_contains_new_core_commands() -> None:
    for name in ("usage", "compress", "title", "retry", "undo", "busy", "reasoning", "details"):
        assert name in COMMANDS


def test_resume_alias_resolution() -> None:
    canonical, args = resolve_command("/resume abc123")
    assert canonical == "resume"
    assert args == "abc123"


def test_session_continuation_lineage() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        db = SessionDB(db_path)
        root = db.create_session(platform="cli", model="m1", title="Root")
        cont = db.create_continuation_session(root)
        session = db.get_session(cont)
        assert session is not None
        assert session["parent_session_id"] == root
        assert session["root_session_id"] == root
    finally:
        Path(db_path).unlink(missing_ok=True)


def test_safety_policy_requires_approval_for_risky_tool_by_default() -> None:
    policy = SafetyPolicy()
    decision = policy.evaluate("terminal", {"command": "rm -rf /tmp/x"}, approval_granted=False)
    assert decision.allowed is False
    assert decision.requires_approval is True


def test_registry_blocks_without_approval_and_allows_with_approval() -> None:
    reg = ToolRegistry()
    reg.register(
        name="terminal",
        toolset="terminal",
        schema={"name": "terminal", "description": "", "parameters": {}},
        handler=lambda args, **kw: json.dumps({"ok": True}),
    )

    blocked = json.loads(
        reg.dispatch(
            "terminal",
            {"command": "echo hi"},
            approval_granted=False,
            enforce_safety=True,
        )
    )
    assert blocked.get("error") == "approval_required"

    allowed = json.loads(
        reg.dispatch(
            "terminal",
            {"command": "echo hi"},
            approval_granted=True,
            enforce_safety=True,
        )
    )
    assert allowed.get("ok") is True
