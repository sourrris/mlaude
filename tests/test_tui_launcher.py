from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from mlaude.tui_gateway.launcher import build_launcher_env, can_launch_tui


def test_can_launch_tui_requires_tty(monkeypatch) -> None:
    monkeypatch.setattr("sys.stdin", SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr("sys.stdout", SimpleNamespace(isatty=lambda: True))
    ok, reason = can_launch_tui()
    assert ok is False
    assert reason == "TTY not detected"


def test_can_launch_tui_accepts_tty(monkeypatch) -> None:
    monkeypatch.setattr("sys.stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr("sys.stdout", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
    ok, reason = can_launch_tui()
    assert ok is True
    assert reason == "ok"


def test_build_launcher_env_sets_resume_and_python_paths(monkeypatch) -> None:
    monkeypatch.setattr("mlaude.tui_gateway.launcher.resolve_tui_dir", lambda: Path("/tmp/tui"))
    env = build_launcher_env(
        cwd="/tmp/project",
        resume_id="sess-123",
        provider="openai",
        model="gpt-test",
        base_url="http://127.0.0.1:9999",
        temperature=0.4,
        yolo=True,
        skin="default",
        tui_dev=False,
    )
    assert env["MLAUDE_CWD"] == "/tmp/project"
    assert env["MLAUDE_TUI_RESUME"] == "sess-123"
    assert env["MLAUDE_TUI_PROVIDER"] == "openai"
    assert env["MLAUDE_DEFAULT_CHAT_MODEL"] == "gpt-test"
    assert env["MLAUDE_LLM_BASE_URL"] == "http://127.0.0.1:9999"
    assert env["MLAUDE_DEFAULT_TEMPERATURE"] == "0.4"
    assert env["MLAUDE_SAFETY_APPROVAL_MODE"] == "yolo"
