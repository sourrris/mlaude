"""Fullscreen chat UI primitives for the interactive CLI."""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass
from typing import Callable

from prompt_toolkit.application import Application
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import D
from prompt_toolkit.styles import Style
from prompt_toolkit.utils import get_cwidth
from prompt_toolkit.widgets import TextArea

logger = logging.getLogger(__name__)
_RICH_TAG_RE = re.compile(r"\[[^\]]*]")


def format_token_count(tokens: int) -> str:
    """Return a compact human-readable token count."""
    if tokens >= 1_000_000:
        value = tokens / 1_000_000
        rounded = round(value)
        return f"{rounded}M" if abs(value - rounded) < 0.05 else f"{value:.1f}M"
    if tokens >= 1_000:
        value = tokens / 1_000
        rounded = round(value)
        return f"{rounded}K" if abs(value - rounded) < 0.05 else f"{value:.1f}K"
    return str(tokens)


def build_assistant_header(
    assistant_name: str,
    assistant_icon: str,
    width: int = 72,
) -> str:
    """Build the Hermes-style assistant separator header."""
    label = " ".join(part for part in (assistant_icon.strip(), assistant_name.strip()) if part).strip()
    prefix = f"  {label}  " if label else "  "
    rule_width = max(8, width - len(prefix))
    return f"{prefix}{'─' * rule_width}"


def build_status_line(
    *,
    model_label: str,
    provider_label: str | None = None,
    turn_tokens: int | None = None,
    session_tokens: int | None = None,
    api_calls: int | None = None,
    busy: bool = False,
    stop_reason: str | None = None,
) -> str:
    """Build a footer line using only real runtime metrics."""
    parts: list[str] = []
    if provider_label:
        parts.append(provider_label)
    if model_label:
        parts.append(model_label)
    if turn_tokens is not None:
        parts.append(f"turn {format_token_count(turn_tokens)}")
    if session_tokens is not None:
        parts.append(f"session {format_token_count(session_tokens)}")
    if api_calls:
        parts.append(f"{api_calls} API call{'s' if api_calls != 1 else ''}")
    parts.append("busy" if busy else "idle")
    if stop_reason and stop_reason != "complete":
        parts.append(stop_reason)
    return " | ".join(parts)


def build_notice_line(text: str, prefix: str = "•") -> str:
    """Render a compact transcript notice line."""
    return f"{prefix} {text}".rstrip()


def strip_rich_markup(text: str) -> str:
    """Remove Rich markup tags from banner text before rendering in prompt-toolkit."""
    return _RICH_TAG_RE.sub("", text)


def prompt_column_width(prompt: str) -> int:
    """Return a safe prompt column width for unicode prompt symbols."""
    normalized = prompt.rstrip() or ">"
    return max(4, get_cwidth(normalized) + 2)


def build_startup_banner(
    *,
    agent_name: str,
    version: str,
    welcome_text: str,
    helper_text: str,
    logo_text: str = "",
    width: int = 72,
) -> list[str]:
    """Build a plain-text startup banner that survives prompt-toolkit rendering."""
    lines: list[str] = []
    title = f"{agent_name} v{version}".strip()
    rule_width = max(12, width - get_cwidth(title) - 3)
    lines.append(f" {title} {'═' * rule_width}")

    if logo_text and width >= 60:
        logo_lines = [
            line.rstrip()
            for line in strip_rich_markup(logo_text).splitlines()
            if line.strip()
        ]
        lines.extend(logo_lines)

    lines.append(welcome_text)
    lines.append(build_notice_line(helper_text))
    return lines


@dataclass
class TranscriptEntry:
    """Simple transcript item."""

    text: str
    style: str = "class:transcript"


class FullscreenChatShell:
    """Prompt-toolkit full-screen shell with transcript, footer, and input bar."""

    def __init__(
        self,
        *,
        history_file: str,
        completer,
        style: Style,
        on_submit: Callable[[str], None],
        on_interrupt: Callable[[], bool],
        on_exit: Callable[[], None],
        initial_prompt: str = "> ",
    ) -> None:
        self._style = style
        self._on_submit = on_submit
        self._on_interrupt = on_interrupt
        self._on_exit = on_exit
        self._prompt = self._normalize_prompt(initial_prompt)
        self._status_text = ""
        self._placeholder = ""
        self._approval_mode = False
        self._transcript_entries: list[TranscriptEntry] = []
        self._transcript_lock = threading.Lock()

        self.transcript = TextArea(
            text="",
            read_only=True,
            focusable=False,
            scrollbar=True,
            wrap_lines=True,
            style="class:transcript",
        )
        self.input_field = TextArea(
            multiline=False,
            wrap_lines=False,
            history=FileHistory(history_file),
            completer=completer,
            complete_while_typing=True,
            auto_suggest=AutoSuggestFromHistory(),
            style="class:input-area",
            prompt="",
        )
        self.input_field.buffer.accept_handler = self._accept_buffer

        status_bar = Window(
            height=1,
            style="class:status-bar",
            content=FormattedTextControl(self._get_status_fragments),
        )
        input_rule = Window(height=1, char="─", style="class:input-rule")
        self.prompt_window = Window(
            width=D.exact(prompt_column_width(self._prompt)),
            height=1,
            style="class:prompt",
            content=FormattedTextControl(self._get_prompt_fragments),
        )
        input_row = VSplit(
            [
                self.prompt_window,
                Window(width=1, char=" ", style="class:input-shell"),
                self.input_field,
            ],
            height=1,
            style="class:input-shell",
        )

        root = HSplit(
            [
                self.transcript,
                status_bar,
                input_rule,
                input_row,
                Window(height=1, char="─", style="class:input-rule"),
            ]
        )

        bindings = KeyBindings()

        @bindings.add("c-c")
        def _handle_ctrl_c(event) -> None:
            if self._approval_mode:
                self._resolve_approval(False)
                return
            if self._on_interrupt():
                self.invalidate()
                return
            self._on_exit()
            event.app.exit()

        self.application = Application(
            layout=Layout(root, focused_element=self.input_field),
            key_bindings=bindings,
            style=self._style,
            full_screen=True,
        )
        logger.debug("Initialized fullscreen shell with prompt=%r width=%s", self._prompt, prompt_column_width(self._prompt))

    def run(self) -> None:
        self.application.run()

    def exit(self) -> None:
        self.application.exit()

    def invalidate(self) -> None:
        self.application.invalidate()

    def set_style(self, style: Style) -> None:
        self._style = style
        self.application.style = style
        self.invalidate()

    def set_prompt(self, prompt: str) -> None:
        self._prompt = self._normalize_prompt(prompt)
        self.prompt_window.width = D.exact(prompt_column_width(self._prompt))
        logger.debug("Updated prompt to %r width=%s", self._prompt, prompt_column_width(self._prompt))
        self.invalidate()

    def set_status(self, text: str) -> None:
        self._status_text = text
        self.invalidate()

    def set_placeholder(self, text: str) -> None:
        self._placeholder = text
        self.invalidate()

    def set_busy(self, busy: bool, message: str = "") -> None:
        self._approval_mode = False
        if busy and message:
            self.set_placeholder(message)
        elif not busy:
            self.set_placeholder("")

    def append_text(self, text: str, style: str = "class:transcript") -> None:
        lines = text.splitlines() or [""]
        with self._transcript_lock:
            for line in lines:
                self._transcript_entries.append(TranscriptEntry(line, style))
            self._refresh_transcript_locked()
        self.invalidate()

    def append_blank_line(self) -> None:
        self.append_text("")

    def append_block(self, lines: list[str], style: str = "class:transcript") -> None:
        with self._transcript_lock:
            for line in lines:
                self._transcript_entries.append(TranscriptEntry(line, style))
            self._refresh_transcript_locked()
        self.invalidate()

    def prompt_for_approval(self, tool: str) -> bool:
        event = threading.Event()
        state: dict[str, bool] = {"approved": False}
        self._approval_event = event
        self._approval_state = state
        self._approval_mode = True
        self.set_prompt("approve>")
        self.set_placeholder(f"Approve {tool}? y/N")
        self.invalidate()
        event.wait()
        self._approval_mode = False
        self.set_prompt("> ")
        self.set_placeholder("")
        self.invalidate()
        return state["approved"]

    def _resolve_approval(self, approved: bool) -> None:
        event = getattr(self, "_approval_event", None)
        state = getattr(self, "_approval_state", None)
        if event is not None and state is not None:
            state["approved"] = approved
            event.set()

    def _accept_buffer(self, buffer: Buffer) -> bool:
        text = buffer.text.strip()
        buffer.text = ""
        if not text:
            return False
        if self._approval_mode:
            self._resolve_approval(text.lower() in {"y", "yes"})
            return False
        self._on_submit(text)
        return False

    def _refresh_transcript_locked(self) -> None:
        text = "\n".join(entry.text for entry in self._transcript_entries)
        self.transcript.buffer.set_document(
            Document(text=text, cursor_position=len(text)),
            bypass_readonly=True,
        )

    def _get_prompt_fragments(self):
        return [("class:prompt", self._prompt)]

    def _get_status_fragments(self):
        return [("class:status-bar", f" {self._status_text}")]

    @staticmethod
    def _normalize_prompt(prompt: str) -> str:
        normalized = prompt.rstrip() or ">"
        return f"{normalized} "
