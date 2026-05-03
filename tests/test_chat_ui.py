from __future__ import annotations

from mlaude.chat_ui import (
    build_assistant_header,
    build_notice_line,
    build_startup_banner,
    build_status_line,
    format_token_count,
    prompt_column_width,
    strip_rich_markup,
)


def test_format_token_count_compacts_large_values() -> None:
    assert format_token_count(999) == "999"
    assert format_token_count(13_500) == "13.5K"
    assert format_token_count(1_000_000) == "1M"


def test_build_assistant_header_includes_label_and_rule() -> None:
    header = build_assistant_header("mlaude", "☠", width=32)
    assert header.startswith("  ☠ mlaude  ")
    assert "─" in header


def test_build_notice_line_renders_prefix() -> None:
    assert build_notice_line("hello") == "• hello"
    assert build_notice_line("warning", prefix="!") == "! warning"


def test_build_status_line_uses_real_metrics_only() -> None:
    assert build_status_line(model_label="claude-sonnet-4.6", busy=False) == "claude-sonnet-4.6 | idle"
    assert build_status_line(
        model_label="claude-sonnet-4.6",
        provider_label="Anthropic",
        turn_tokens=13_500,
        session_tokens=1_000_000,
        api_calls=2,
        busy=True,
        stop_reason="budget_exhausted",
    ) == (
        "Anthropic | claude-sonnet-4.6 | turn 13.5K | session 1M | "
        "2 API calls | busy | budget_exhausted"
    )


def test_strip_rich_markup_removes_tags() -> None:
    assert strip_rich_markup("[bold #FFD700]MLAUDE[/]") == "MLAUDE"


def test_prompt_column_width_handles_longer_prompts() -> None:
    assert prompt_column_width("❯ ") >= 4
    assert prompt_column_width("approve> ") >= len("approve>") + 1


def test_build_startup_banner_includes_plain_logo_and_help() -> None:
    lines = build_startup_banner(
        agent_name="mlaude",
        version="0.3.0-dev",
        welcome_text="Welcome",
        helper_text="Use /help",
        logo_text="[bold]ASCII[/]\n[#aaa]LOGO[/]",
        width=72,
    )
    assert lines[0].startswith(" mlaude v0.3.0-dev ")
    assert "ASCII" in lines[1]
    assert "LOGO" in lines[2]
    assert lines[-2] == "Welcome"
    assert lines[-1] == "• Use /help"
