from __future__ import annotations

import io
from dataclasses import dataclass

from rich.console import Console
from rich.table import Table

from mlaude.banner import VERSION
from mlaude.commands import COMMANDS_BY_CATEGORY
from mlaude.display import get_tool_emoji
from mlaude.providers.registry import get_provider_label, list_providers
from mlaude.settings import MLAUDE_HOME
from mlaude.state import SessionDB


def _capture(renderer) -> str:
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, color_system=None, width=100)
    renderer(console)
    return buf.getvalue().rstrip()


def render_help() -> str:
    def _renderer(out: Console) -> None:
        from mlaude.skin_engine import get_active_help_header

        out.print(f"\n  [bold]{get_active_help_header()}[/bold]\n")
        for category, cmds in COMMANDS_BY_CATEGORY.items():
            table = Table(
                show_header=False,
                box=None,
                padding=(0, 2),
                title=f"[bold]{category}[/bold]",
                title_style="dim",
            )
            for cmd in cmds:
                aliases = f" [dim]({', '.join(cmd.aliases)})[/dim]" if cmd.aliases else ""
                args = f" [dim]{cmd.args_hint}[/dim]" if cmd.args_hint else ""
                table.add_row(
                    f"[bold bright_yellow]/{cmd.name}[/bold bright_yellow]{args}",
                    f"{cmd.description}{aliases}",
                )
            out.print(table)
            out.print()

    return _capture(_renderer)


def render_tools() -> str:
    def _renderer(out: Console) -> None:
        from mlaude.tools.registry import registry

        tools = registry.get_all()
        if not tools:
            out.print("[dim]No tools loaded.[/dim]")
            return

        table = Table(title="[bold]Available Tools[/bold]", border_style="dim")
        table.add_column("Tool", style="bold")
        table.add_column("Toolset", style="dim")
        table.add_column("Available", justify="center")
        for name, entry in sorted(tools.items()):
            emoji = get_tool_emoji(name)
            avail = "✓" if entry.is_available() else "✗"
            style = "green" if entry.is_available() else "red"
            table.add_row(f"{emoji} {name}", entry.toolset, f"[{style}]{avail}[/{style}]")
        out.print(table)

    return _capture(_renderer)


def render_toolsets() -> str:
    def _renderer(out: Console) -> None:
        from mlaude.toolsets import TOOLSETS

        table = Table(title="[bold]Available Toolsets[/bold]", border_style="dim")
        table.add_column("Toolset", style="bold bright_yellow")
        table.add_column("Description", style="dim")
        table.add_column("Tools / Includes")
        for ts_name, ts_def in sorted(TOOLSETS.items()):
            desc = ts_def.get("description", "")
            tools_list = ", ".join(ts_def.get("tools", []))
            includes_list = ", ".join(f"[{item}]" for item in ts_def.get("includes", []))
            detail = " ".join(filter(None, [tools_list, includes_list]))
            table.add_row(ts_name, desc, detail or "—")
        out.print(table)

    return _capture(_renderer)


def render_skills() -> str:
    def _renderer(out: Console) -> None:
        from mlaude.settings import SKILLS_DIR

        SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        skill_files = sorted(SKILLS_DIR.glob("**/*.md"))
        if not skill_files:
            out.print(
                f"[dim]No skills found in [bold]{SKILLS_DIR}[/bold].\n"
                "  Ask the agent to create a skill, or add a .md file there.[/dim]"
            )
            return

        table = Table(title="[bold]Skills[/bold]", border_style="dim")
        table.add_column("Name", style="bold bright_yellow")
        table.add_column("Title")
        table.add_column("Size", justify="right", style="dim")
        for file_path in skill_files:
            rel = file_path.relative_to(SKILLS_DIR)
            content = file_path.read_text(encoding="utf-8", errors="replace")
            title = next(
                (line[2:].strip() for line in content.splitlines() if line.startswith("# ")),
                str(rel.stem),
            )
            table.add_row(str(rel).replace(".md", ""), title, f"{len(content):,} B")
        out.print(table)
        out.print(f"  [dim]Skills directory: {SKILLS_DIR}[/dim]")

    return _capture(_renderer)


def render_sessions(db: SessionDB) -> str:
    def _renderer(out: Console) -> None:
        sessions = db.list_sessions(limit=15)
        if not sessions:
            out.print("[dim]No sessions yet.[/dim]")
            return
        table = Table(title="[bold]Recent Sessions[/bold]", border_style="dim")
        table.add_column("ID", style="dim", max_width=12)
        table.add_column("Title")
        table.add_column("Platform", style="dim")
        table.add_column("Updated", style="dim")
        for session in sessions:
            table.add_row(
                session["id"][:12],
                session.get("title", "") or "(untitled)",
                session.get("platform", ""),
                session.get("updated_at", "")[:19],
            )
        out.print(table)

    return _capture(_renderer)


def render_stats(db: SessionDB) -> str:
    stats = db.get_stats()
    return (
        f"Sessions: {stats['sessions']}  "
        f"Messages: {stats['messages']}  "
        f"Tokens: {stats['total_tokens']:,}"
    )


def render_skins() -> str:
    def _renderer(out: Console) -> None:
        from mlaude.skin_engine import get_active_skin_name, list_skins

        active = get_active_skin_name()
        table = Table(title="[bold]Available Skins[/bold]", border_style="dim")
        table.add_column("Name", style="bold")
        table.add_column("Description")
        table.add_column("Source", style="dim")
        table.add_column("Active", justify="center")
        for skin in list_skins():
            is_active = "✓" if skin["name"] == active else ""
            name_style = "bold bright_yellow" if skin["name"] == active else "bold"
            table.add_row(
                f"[{name_style}]{skin['name']}[/{name_style}]",
                skin["description"],
                skin["source"],
                f"[green]{is_active}[/green]",
            )
        out.print(table)

    return _capture(_renderer)


def render_providers() -> str:
    def _renderer(out: Console) -> None:
        table = Table(title="[bold]Available Providers[/bold]", border_style="dim")
        table.add_column("Provider", style="bold")
        table.add_column("Name")
        table.add_column("Configured", justify="center")
        table.add_column("Env Vars", style="dim")
        for provider in list_providers():
            style = "green" if provider["configured"] == "✓" else "red"
            table.add_row(
                provider["id"],
                provider["name"],
                f"[{style}]{provider['configured']}[/{style}]",
                provider["env_vars"],
            )
        out.print(table)

    return _capture(_renderer)


def render_config(*, model: str, base_url: str, temperature: float, provider: str) -> str:
    def _renderer(out: Console) -> None:
        from mlaude.skin_engine import get_active_skin_name

        table = Table(title="[bold]Current Configuration[/bold]", border_style="dim")
        table.add_column("Setting", style="bold")
        table.add_column("Value")
        table.add_row("Model", model)
        table.add_row("Provider", provider or "auto")
        table.add_row("Provider Label", get_provider_label(provider or "local"))
        table.add_row("Base URL", base_url)
        table.add_row("Temperature", str(temperature))
        table.add_row("Skin", get_active_skin_name())
        table.add_row("Home", str(MLAUDE_HOME))
        table.add_row("Version", VERSION)
        out.print(table)

    return _capture(_renderer)


def render_history(db: SessionDB, session_id: str) -> str:
    messages = db.get_messages(session_id, limit=20)
    if not messages:
        return "No history."
    return "\n".join(
        f"{message['role']}: {(message.get('content') or '')[:100]}" for message in messages
    )


@dataclass
class TranscriptEntry:
    role: str
    content: str
    name: str = ""
    reasoning: str = ""


def build_transcript(db: SessionDB, session_id: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for message in db.get_openai_messages(session_id):
        role = str(message.get("role", "assistant"))
        content = str(message.get("content", "") or "")
        if role == "tool":
            label = message.get("name", "tool")
            entries.append({"kind": "tool", "role": role, "name": str(label), "content": content})
            continue
        if role == "assistant" and message.get("reasoning"):
            entries.append(
                {
                    "kind": "reasoning",
                    "role": role,
                    "content": str(message.get("reasoning", "")),
                }
            )
        entries.append({"kind": "message", "role": role, "content": content})
    return entries
