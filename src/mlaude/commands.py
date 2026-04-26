"""Slash command registry and definitions.

Central registry for all slash commands — CLI, gateway, and autocomplete
all derive from this single source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CommandDef:
    """A single slash command definition."""

    name: str
    description: str
    category: str  # Session, Configuration, Tools & Skills, Info, Exit
    aliases: tuple[str, ...] = ()
    args_hint: str = ""
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
    CommandDef("delete", "Delete a session", "Session", args_hint="<session_id>"),

    # Configuration
    CommandDef("model", "Show or change the model", "Configuration", args_hint="[model_name]"),
    CommandDef("provider", "Show or change the provider", "Configuration", args_hint="[provider]"),
    CommandDef("temperature", "Show or change temperature", "Configuration", aliases=("temp",), args_hint="[value]"),
    CommandDef("system", "Show or set system prompt", "Configuration", args_hint="[prompt]"),

    # Tools & Skills
    CommandDef("tools", "List available tools", "Tools & Skills"),
    CommandDef("toolsets", "List available toolsets", "Tools & Skills"),
    CommandDef("skills", "List or manage skills", "Tools & Skills", args_hint="[list|view|add]"),

    # Info
    CommandDef("help", "Show this help", "Info", aliases=("h", "?")),
    CommandDef("stats", "Show session statistics", "Info"),
    CommandDef("version", "Show version", "Info"),
    CommandDef("debug", "Toggle debug mode", "Info"),

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
