"""Display utilities — spinner, tool formatting, token usage.

Provides the visual polish for the CLI experience.
"""

from __future__ import annotations

import itertools
import sys
import threading
import time
from typing import Any


# ---------------------------------------------------------------------------
# Spinner
# ---------------------------------------------------------------------------

_THINKING_FACES = ["(⊙_⊙)", "(◕‿◕)", "(≧▽≦)", "(╹◡╹)", "(✿◠‿◠)", "(◉‿◉)"]
_THINKING_VERBS = [
    "thinking", "pondering", "reasoning", "analyzing", "considering",
    "processing", "evaluating", "contemplating",
]

_TOOL_EMOJIS: dict[str, str] = {
    "read_file": "📄",
    "write_file": "✏️",
    "patch": "🩹",
    "search_files": "🔍",
    "terminal": "💻",
    "web_search": "🌐",
    "web_extract": "📰",
    "browser_navigate": "🌍",
    "delegate_task": "🤖",
    "memory": "🧠",
    "todo": "📋",
    "skills_list": "📚",
}


def get_tool_emoji(tool_name: str) -> str:
    """Get the emoji for a tool name."""
    return _TOOL_EMOJIS.get(tool_name, "⚡")


class Spinner:
    """Animated thinking spinner for the CLI."""

    def __init__(self, style: str = "kawaii"):
        self._running = False
        self._thread: threading.Thread | None = None
        self._message = ""

        if style == "kawaii":
            self._frames = _THINKING_FACES
            self._verbs = _THINKING_VERBS
        else:
            self._frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            self._verbs = _THINKING_VERBS

    def start(self, message: str = "") -> None:
        self._message = message
        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        # Clear the spinner line
        sys.stderr.write("\r\033[K")
        sys.stderr.flush()

    def update(self, message: str) -> None:
        self._message = message

    def _spin(self) -> None:
        frames = itertools.cycle(self._frames)
        verbs = itertools.cycle(self._verbs)
        verb = next(verbs)
        tick = 0

        while self._running:
            face = next(frames)
            extra = f" {self._message}" if self._message else ""
            sys.stderr.write(f"\r\033[K  {face} {verb}...{extra}")
            sys.stderr.flush()
            time.sleep(0.3)
            tick += 1
            if tick % 8 == 0:
                verb = next(verbs)


# ---------------------------------------------------------------------------
# Tool activity formatting
# ---------------------------------------------------------------------------


def format_tool_start(name: str, args: dict) -> str:
    """Format a tool invocation for display."""
    emoji = get_tool_emoji(name)
    args_preview = ", ".join(
        f"{k}={repr(v)[:50]}" for k, v in list(args.items())[:3]
    )
    return f"  [dim]┊[/dim] {emoji} [bold yellow]{name}[/bold yellow]({args_preview})"


def format_tool_end(name: str, result: str) -> str:
    """Format a tool result for display."""
    preview = result[:200].replace("\n", " ")
    if len(result) > 200:
        preview += "…"
    return f"  [dim]┊ → {preview}[/dim]"


def format_token_usage(usage: dict) -> str:
    """Format token usage for display."""
    prompt = usage.get("prompt_tokens", 0)
    completion = usage.get("completion_tokens", 0)
    total = usage.get("total_tokens", prompt + completion)
    return f"[dim]tokens: {total:,} (prompt: {prompt:,}, completion: {completion:,})[/dim]"
