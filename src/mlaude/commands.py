"""Slash command registry, autocomplete, and definitions.

Central registry for all slash commands — CLI, gateway, and autocomplete
all derive from this single source. Ported from Hermes Agent.
"""

from __future__ import annotations

from dataclasses import dataclass

try:
    from prompt_toolkit.auto_suggest import AutoSuggest, Suggestion
    from prompt_toolkit.completion import Completer, Completion
except ImportError:
    AutoSuggest = object  # type: ignore[assignment,misc]
    Completer = object    # type: ignore[assignment,misc]
    Suggestion = None     # type: ignore[assignment]
    Completion = None     # type: ignore[assignment]


@dataclass
class CommandDef:
    """A single slash command definition."""

    name: str
    description: str
    category: str  # Session, Configuration, Tools & Skills, Info, Exit
    aliases: tuple[str, ...] = ()
    args_hint: str = ""
    subcommands: tuple[str, ...] = ()
    cli_only: bool = False
    gateway_only: bool = False

    @property
    def all_names(self) -> tuple[str, ...]:
        return (self.name,) + self.aliases


COMMAND_REGISTRY: list[CommandDef] = [
    # Session
    CommandDef("new", "Start a new session", "Session", aliases=("clear",)),
    CommandDef("resume", "Resume a previous session", "Session", args_hint="[session_id]"),
    CommandDef("history", "Show session history", "Session"),
    CommandDef("sessions", "List all sessions", "Session"),
    CommandDef("usage", "Show token/cost/session usage", "Session"),
    CommandDef("compress", "Create continuation session with lineage", "Session"),
    CommandDef("title", "Show or set current session title", "Session", args_hint="[new_title]"),
    CommandDef("retry", "Retry last user message", "Session"),
    CommandDef("undo", "Remove last user/assistant turn", "Session"),
    CommandDef("delete", "Delete a session", "Session", args_hint="<session_id>"),
    CommandDef("search", "Search across sessions", "Session", args_hint="<query>"),
    CommandDef("copy", "Copy last response to clipboard", "Session"),

    # Configuration
    CommandDef("model", "Show or change the model", "Configuration", args_hint="[model_name]"),
    CommandDef("provider", "Show or change the provider", "Configuration", args_hint="[provider]"),
    CommandDef("temperature", "Show or change temperature", "Configuration", aliases=("temp",), args_hint="[value]"),
    CommandDef("system", "Show or set system prompt", "Configuration", args_hint="[prompt]"),
    CommandDef("skin", "Show or change the skin theme", "Configuration", args_hint="[name]"),
    CommandDef("config", "Show current configuration", "Configuration"),

    # Tools & Skills
    CommandDef("tools", "List available tools", "Tools & Skills"),
    CommandDef("toolsets", "List available toolsets", "Tools & Skills"),
    CommandDef("skills", "List or manage skills", "Tools & Skills", args_hint="[list|view|add]"),

    # Info
    CommandDef("help", "Show this help", "Info", aliases=("h", "?")),
    CommandDef("stats", "Show session statistics", "Info"),
    CommandDef("version", "Show version", "Info"),
    CommandDef("debug", "Toggle debug mode", "Info"),
    CommandDef("busy", "Show or set busy input mode", "Info", args_hint="[on|off]"),
    CommandDef("reasoning", "Show or set reasoning verbosity", "Info", args_hint="[low|medium|high]"),
    CommandDef("details", "Show or set details mode", "Info", args_hint="[on|off]"),

    # Exit
    CommandDef("quit", "Exit mlaude", "Exit", aliases=("exit", "q", "bye")),
]


# -- Derived lookups --

def _build_commands_dict() -> dict[str, CommandDef]:
    """Flat dict: name/alias → CommandDef."""
    result: dict[str, CommandDef] = {}
    for cmd in COMMAND_REGISTRY:
        for name in cmd.all_names:
            result[name] = cmd
    return result


COMMANDS = _build_commands_dict()

COMMANDS_BY_CATEGORY: dict[str, list[CommandDef]] = {}
for _cmd in COMMAND_REGISTRY:
    COMMANDS_BY_CATEGORY.setdefault(_cmd.category, []).append(_cmd)


def resolve_command(text: str) -> tuple[str, str]:
    """Resolve a slash command to (canonical_name, args_string).

    Returns ("", original_text) if not a valid command.
    """
    if not text.startswith("/"):
        return "", text

    parts = text[1:].split(maxsplit=1)
    cmd_name = parts[0].lower() if parts else ""
    args_str = parts[1] if len(parts) > 1 else ""

    cmd = COMMANDS.get(cmd_name)
    if cmd:
        return cmd.name, args_str

    return "", text


# ---------------------------------------------------------------------------
# Rich autocomplete — Hermes-style slash command completer
# ---------------------------------------------------------------------------


class SlashCommandCompleter(Completer):
    """Autocomplete for built-in slash commands with descriptions and subcommands."""

    def __init__(self) -> None:
        pass

    @staticmethod
    def _completion_text(cmd_name: str, word: str) -> str:
        """Return replacement text for a completion.

        When the user has already typed the full command exactly (/help),
        returning `help` would be a no-op and prompt_toolkit suppresses the
        menu. Appending a trailing space keeps the dropdown visible.
        """
        return f"{cmd_name} " if cmd_name == word else cmd_name

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.lstrip()
        if not text.startswith("/"):
            return

        # Split into command and subcommand parts
        parts = text[1:].split(maxsplit=1)
        cmd_text = parts[0].lower() if parts else ""
        sub_text = parts[1].strip() if len(parts) > 1 else ""
        has_space = " " in text[1:]

        # If we have a complete command + space, offer subcommands
        if has_space and cmd_text:
            cmd = COMMANDS.get(cmd_text)
            if cmd:
                # Skin subcommands
                if cmd.name == "skin":
                    yield from self._skin_completions(sub_text, sub_text.lower())
                    return

                # Provider subcommands
                if cmd.name == "provider":
                    yield from self._provider_completions(sub_text, sub_text.lower())
                    return

                # Session resume — show session IDs
                if cmd.name == "resume":
                    yield from self._session_completions(sub_text, sub_text.lower())
                    return
            return

        # Complete command names
        word = text[1:]  # strip leading /
        word_lower = word.lower()

        # Deduplicate: only show canonical names, not aliases
        seen_names: set[str] = set()
        for cmd in COMMAND_REGISTRY:
            if cmd.name in seen_names:
                continue

            # Check if the canonical name matches
            if cmd.name.startswith(word_lower):
                seen_names.add(cmd.name)
                args = f" {cmd.args_hint}" if cmd.args_hint else ""
                yield Completion(
                    self._completion_text(cmd.name, word),
                    start_position=-len(word),
                    display=f"/{cmd.name}{args}",
                    display_meta=cmd.description,
                )
                continue

            # Check aliases
            for alias in cmd.aliases:
                if alias.startswith(word_lower) and alias not in seen_names:
                    seen_names.add(alias)
                    yield Completion(
                        self._completion_text(alias, word),
                        start_position=-len(word),
                        display=f"/{alias}",
                        display_meta=f"{cmd.description} (→ /{cmd.name})",
                    )

    @staticmethod
    def _skin_completions(sub_text: str, sub_lower: str):
        """Yield completions for /skin from available skins."""
        try:
            from mlaude.skin_engine import list_skins
            for s in list_skins():
                name = s["name"]
                if name.startswith(sub_lower) and name != sub_lower:
                    yield Completion(
                        name,
                        start_position=-len(sub_text),
                        display=name,
                        display_meta=s.get("description", "") or s.get("source", ""),
                    )
        except Exception:
            pass

    @staticmethod
    def _provider_completions(sub_text: str, sub_lower: str):
        """Yield completions for /provider from available providers."""
        try:
            from mlaude.providers.registry import list_providers
            for p in list_providers():
                pid = p["id"]
                if pid.startswith(sub_lower) and pid != sub_lower:
                    yield Completion(
                        pid,
                        start_position=-len(sub_text),
                        display=pid,
                        display_meta=p.get("name", ""),
                    )
        except Exception:
            pass

    @staticmethod
    def _session_completions(sub_text: str, sub_lower: str):
        """Yield completions for /resume from recent sessions."""
        try:
            from mlaude.state import SessionDB
            db = SessionDB()
            sessions = db.list_sessions(limit=10)
            for s in sessions:
                sid = s["id"][:12]
                title = s.get("title", "") or "(untitled)"
                if sid.startswith(sub_lower):
                    yield Completion(
                        sid,
                        start_position=-len(sub_text),
                        display=sid,
                        display_meta=title[:40],
                    )
        except Exception:
            pass


class SlashCommandAutoSuggest(AutoSuggest):
    """Auto-suggest that combines slash command completion with history."""

    def __init__(self, history_suggest=None, completer: SlashCommandCompleter | None = None):
        self._history = history_suggest
        self._completer = completer

    def get_suggestion(self, buffer, document):
        text = document.text_before_cursor

        # Slash command suggestions
        if text.startswith("/") and self._completer:
            try:
                completions = list(self._completer.get_completions(document, None))
                if completions:
                    first = completions[0]
                    remainder = first.text[len(text) - 1:]  # skip the /
                    if remainder:
                        return Suggestion(remainder)
            except Exception:
                pass

        # Fall back to history
        if self._history:
            return self._history.get_suggestion(buffer, document)

        return None
