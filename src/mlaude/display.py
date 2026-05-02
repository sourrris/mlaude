"""Display utilities — kawaii spinner, tool formatting, token usage.
"""
from __future__ import annotations

import itertools
import sys
import threading
import time


# ---------------------------------------------------------------------------
# Default faces & verbs (overridden by active skin)
# ---------------------------------------------------------------------------

_DEFAULT_THINKING_FACES = ["(⊙_⊙)", "(◕‿◕)", "(≧▽≦)", "(╹◡╹)", "(✿◠‿◠)", "(◉‿◉)"]
_DEFAULT_WAITING_FACES = ["(⊙_⊙)", "(◕‿◕)", "(≧▽≦)", "(╹◡╹)", "(✿◠‿◠)", "(◉‿◉)"]
_DEFAULT_THINKING_VERBS = [
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
    "browser_snapshot": "📸",
    "browser_click": "👆",
    "browser_type": "⌨️",
    "browser_scroll": "📜",
    "delegate_task": "🤖",
    "memory": "🧠",
    "todo": "📋",
    "skills_list": "📚",
    "skill_view": "📖",
    "skill_manage": "🔧",
    "code_execution": "🐍",
}


def get_tool_emoji(tool_name: str) -> str:
    """Get the emoji for a tool name. Checks skin overrides first."""
    try:
        from mlaude.skin_engine import get_active_skin
        skin = get_active_skin()
        if skin.tool_emojis and tool_name in skin.tool_emojis:
            return skin.tool_emojis[tool_name]
    except Exception:
        pass
    return _TOOL_EMOJIS.get(tool_name, "⚡")


def _get_tool_prefix() -> str:
    """Get the tool output prefix from the active skin."""
    try:
        from mlaude.skin_engine import get_active_skin
        return get_active_skin().tool_prefix
    except Exception:
        return "┊"


# ---------------------------------------------------------------------------
# Kawaii Spinner with wing support
# ---------------------------------------------------------------------------

class Spinner:
    """Animated thinking spinner for the CLI with skin-aware faces, verbs, and wings."""

    def __init__(self):
        self._running = False
        self._thread: threading.Thread | None = None
        self._message = ""
        self._load_skin_data()

    def _load_skin_data(self) -> None:
        """Load spinner config from the active skin."""
        self._faces = list(_DEFAULT_THINKING_FACES)
        self._waiting_faces = list(_DEFAULT_WAITING_FACES)
        self._verbs = list(_DEFAULT_THINKING_VERBS)
        self._wings: list[tuple[str, str]] = []

        try:
            from mlaude.skin_engine import get_active_skin
            skin = get_active_skin()
            spinner_cfg = skin.spinner
            if spinner_cfg.get("thinking_faces"):
                self._faces = spinner_cfg["thinking_faces"]
            if spinner_cfg.get("waiting_faces"):
                self._waiting_faces = spinner_cfg["waiting_faces"]
            if spinner_cfg.get("thinking_verbs"):
                self._verbs = spinner_cfg["thinking_verbs"]
            self._wings = skin.get_spinner_wings()
        except Exception:
            pass

    def start(self, message: str = "") -> None:
        if self._running:
            return
        self._message = message
        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        sys.stderr.write("\r\033[K")
        sys.stderr.flush()

    def update(self, message: str) -> None:
        self._message = message

    def _spin(self) -> None:
        faces = itertools.cycle(self._faces)
        verbs = itertools.cycle(self._verbs)
        wings_cycle = itertools.cycle(self._wings) if self._wings else None
        verb = next(verbs)
        tick = 0

        while self._running:
            face = next(faces)
            extra = f" {self._message}" if self._message else ""

            if wings_cycle:
                left_wing, right_wing = next(wings_cycle)
                line = f"\r\033[K  {left_wing} {face} {verb}...{extra} {right_wing}"
            else:
                line = f"\r\033[K  {face} {verb}...{extra}"

            sys.stderr.write(line)
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
    prefix = _get_tool_prefix()
    emoji = get_tool_emoji(name)
    args_preview = ", ".join(
        f"{k}={repr(v)[:50]}" for k, v in list(args.items())[:3]
    )
    return f"  [dim]{prefix}[/dim] {emoji} [bold yellow]{name}[/bold yellow]({args_preview})"


def format_tool_end(name: str, result: str) -> str:
    """Format a tool result for display."""
    prefix = _get_tool_prefix()
    preview = result[:200].replace("\n", " ")
    if len(result) > 200:
        preview += "…"
    return f"  [dim]{prefix} → {preview}[/dim]"


def format_token_usage(usage: dict) -> str:
    """Format token usage for display."""
    prompt = usage.get("prompt_tokens", 0)
    completion = usage.get("completion_tokens", 0)
    total = usage.get("total_tokens", prompt + completion)
    return f"[dim]tokens: {total:,} (prompt: {prompt:,}, completion: {completion:,})[/dim]"
