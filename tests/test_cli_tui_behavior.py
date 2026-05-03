from __future__ import annotations

from types import SimpleNamespace

from typer.testing import CliRunner

from mlaude import cli


class _FakeSessionDB:
    def list_sessions(self, limit: int = 1):
        return []


class _FakeAgent:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        temperature: float,
        quiet_mode: bool,
        provider: str | None,
        session_db,
    ) -> None:
        self.base_url = base_url
        self.model = model
        self.temperature = temperature
        self.provider_name = provider
        self.session_id = "test-session"


def test_main_exits_cleanly_without_tty(monkeypatch) -> None:
    runner = CliRunner()

    monkeypatch.setattr("sys.stdin", SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr("sys.stdout", SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr(cli, "ensure_app_dirs", lambda: None)
    monkeypatch.setattr(cli, "prefetch_update_check", lambda: None)
    monkeypatch.setattr(cli, "discover_tools", lambda: None)
    monkeypatch.setattr(cli, "SessionDB", _FakeSessionDB)
    monkeypatch.setattr(cli, "MLaudeAgent", _FakeAgent)
    monkeypatch.setattr(cli, "_run_fullscreen_chat", lambda state: (_ for _ in ()).throw(AssertionError()))

    result = runner.invoke(cli.app, [])

    assert result.exit_code == 1
    assert "Interactive mode requires a TTY." in result.output
    assert "--message" in result.output
    assert "non-interactive runs" in result.output


def test_main_launches_tui_without_constructing_agent(monkeypatch) -> None:
    runner = CliRunner()
    launched: dict[str, object] = {}

    monkeypatch.setattr("sys.stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr("sys.stdout", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(cli, "ensure_app_dirs", lambda: None)
    monkeypatch.setattr(cli, "prefetch_update_check", lambda: None)
    monkeypatch.setattr(cli, "load_config", lambda: {})
    monkeypatch.setattr(cli, "SessionDB", _FakeSessionDB)
    monkeypatch.setattr(cli, "can_launch_tui", lambda: (True, "ok"))
    def _fake_launch_tui(**kwargs):
        launched["kwargs"] = kwargs
        return 0

    monkeypatch.setattr(cli, "launch_tui", _fake_launch_tui)

    def _fail_agent(**kwargs):
        raise AssertionError("interactive TUI path should not construct an agent")

    monkeypatch.setattr(cli, "MLaudeAgent", _fail_agent)

    result = runner.invoke(cli.app, [])

    assert result.exit_code == 0
    assert launched["kwargs"]["tui_dev"] is False
