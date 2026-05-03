"""CLI entry point 

Full interactive CLI with Rich panels, animated spinners, slash command
autocomplete, session management, skin engine, and tool activity display.
"""

from __future__ import annotations

import io
import logging
import os
import signal
import shutil
import threading
from dataclasses import dataclass

import typer
from prompt_toolkit.styles import Style as PTStyle
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from mlaude.agent import MLaudeAgent
from mlaude.banner import VERSION, prefetch_update_check
from mlaude.chat_ui import (
    FullscreenChatShell,
    build_assistant_header,
    build_notice_line,
    build_startup_banner,
    build_status_line,
)
from mlaude.commands import (
    COMMANDS_BY_CATEGORY,
    resolve_command,
    SlashCommandCompleter,
)
from mlaude.display import Spinner, get_tool_emoji
from mlaude.model_tools import discover_tools
from mlaude.settings import (
    DEFAULT_CHAT_MODEL,
    DEFAULT_TEMPERATURE,
    LLM_BASE_URL,
    MLAUDE_HOME,
    ensure_app_dirs,
    load_config,
    save_config_value,
)
from mlaude.state import SessionDB
from mlaude.safety import policy as safety_policy
from mlaude.tui_gateway.launcher import TuiLaunchError, can_launch_tui, launch_tui

app = typer.Typer(name="mlaude", invoke_without_command=True)
console = Console()
logger = logging.getLogger(__name__)


def _ensure_interactive_tty() -> None:
    """Fail fast before prompt-toolkit tries to boot on a non-terminal stream."""
    ok, reason = can_launch_tui()
    if ok:
        return
    if reason == "TTY not detected":
        console.print(
            f"[bold red]Interactive mode requires a TTY.[/bold red] "
            f"[dim]({reason}; use --message for non-interactive runs)[/dim]"
        )
    else:
        console.print(
            f"[bold red]Interactive TUI is unavailable.[/bold red] "
            f"[dim]({reason})[/dim]"
        )
    raise typer.Exit(code=1)


def _launch_tui(
    *,
    cwd: str,
    resume_id: str | None,
    provider: str | None,
    model: str,
    base_url: str,
    temperature: float,
    yolo: bool,
    skin: str | None,
    tui_dev: bool,
) -> None:
    try:
        code = launch_tui(
            cwd=cwd,
            resume_id=resume_id,
            provider=provider,
            model=model,
            base_url=base_url,
            temperature=temperature,
            yolo=yolo,
            skin=skin,
            tui_dev=tui_dev,
        )
    except TuiLaunchError as exc:
        console.print(f"[bold red]Failed to launch TUI:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    if code != 0:
        console.print(f"[bold red]TUI exited with status {code}.[/bold red]")
        raise typer.Exit(code=code)


# ---------------------------------------------------------------------------
# Slash command handlers
# ---------------------------------------------------------------------------


def _show_help(out: Console | None = None) -> None:
    out = out or console
    from mlaude.skin_engine import get_active_help_header
    header = get_active_help_header()
    out.print(f"\n  [bold]{header}[/bold]\n")

    for category, cmds in COMMANDS_BY_CATEGORY.items():
        table = Table(
            show_header=False, box=None, padding=(0, 2),
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


def _show_tools(out: Console | None = None) -> None:
    out = out or console
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


def _show_toolsets(out: Console | None = None) -> None:
    out = out or console
    from mlaude.toolsets import TOOLSETS

    table = Table(title="[bold]Available Toolsets[/bold]", border_style="dim")
    table.add_column("Toolset", style="bold bright_yellow")
    table.add_column("Description", style="dim")
    table.add_column("Tools / Includes")

    for ts_name, ts_def in sorted(TOOLSETS.items()):
        desc = ts_def.get("description", "")
        tools_list = ", ".join(ts_def.get("tools", []))
        includes_list = ", ".join(f"[{i}]" for i in ts_def.get("includes", []))
        detail = " ".join(filter(None, [tools_list, includes_list]))
        table.add_row(ts_name, desc, detail or "—")

    out.print(table)


def _show_skills(out: Console | None = None) -> None:
    out = out or console
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

    for f in skill_files:
        rel = f.relative_to(SKILLS_DIR)
        content = f.read_text(encoding="utf-8", errors="replace")
        title = next(
            (line[2:].strip() for line in content.splitlines() if line.startswith("# ")),
            str(rel.stem),
        )
        size = f"{len(content):,} B"
        table.add_row(str(rel).replace(".md", ""), title, size)

    out.print(table)
    out.print(f"  [dim]Skills directory: {SKILLS_DIR}[/dim]")


def _show_sessions(db: SessionDB, out: Console | None = None) -> None:
    out = out or console
    sessions = db.list_sessions(limit=15)
    if not sessions:
        out.print("[dim]No sessions yet.[/dim]")
        return

    table = Table(title="[bold]Recent Sessions[/bold]", border_style="dim")
    table.add_column("ID", style="dim", max_width=12)
    table.add_column("Title")
    table.add_column("Platform", style="dim")
    table.add_column("Updated", style="dim")

    for s in sessions:
        table.add_row(
            s["id"][:12],
            s.get("title", "") or "(untitled)",
            s.get("platform", ""),
            s.get("updated_at", "")[:19],
        )

    out.print(table)


def _show_stats(db: SessionDB, out: Console | None = None) -> None:
    out = out or console
    stats = db.get_stats()
    out.print(
        f"  [bold]Sessions:[/bold] {stats['sessions']}  "
        f"[bold]Messages:[/bold] {stats['messages']}  "
        f"[bold]Tokens:[/bold] {stats['total_tokens']:,}"
    )


def _show_skins(out: Console | None = None) -> None:
    out = out or console
    from mlaude.skin_engine import list_skins, get_active_skin_name

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


def _show_providers(out: Console | None = None) -> None:
    out = out or console
    from mlaude.providers.registry import list_providers

    table = Table(title="[bold]Available Providers[/bold]", border_style="dim")
    table.add_column("Provider", style="bold")
    table.add_column("Name")
    table.add_column("Configured", justify="center")
    table.add_column("Env Vars", style="dim")

    for p in list_providers():
        style = "green" if p["configured"] == "✓" else "red"
        table.add_row(
            p["id"],
            p["name"],
            f"[{style}]{p['configured']}[/{style}]",
            p["env_vars"],
        )

    out.print(table)


def _show_config(
    model: str,
    base_url: str,
    temperature: float,
    provider: str,
    out: Console | None = None,
) -> None:
    out = out or console
    from mlaude.skin_engine import get_active_skin_name

    table = Table(title="[bold]Current Configuration[/bold]", border_style="dim")
    table.add_column("Setting", style="bold")
    table.add_column("Value")

    table.add_row("Model", model)
    table.add_row("Provider", provider or "auto")
    table.add_row("Base URL", base_url)
    table.add_row("Temperature", str(temperature))
    table.add_row("Skin", get_active_skin_name())
    table.add_row("Home", str(MLAUDE_HOME))

    out.print(table)


def _capture_console_output(renderer) -> str:
    """Capture a helper that writes to a Rich console and return plain text."""
    buf = io.StringIO()
    temp_console = Console(file=buf, force_terminal=False, color_system=None, width=100)
    renderer(temp_console)
    return buf.getvalue().rstrip()


@dataclass
class _InteractiveState:
    agent: MLaudeAgent
    db: SessionDB
    model: str
    base_url: str
    temperature: float
    current_provider: str | None
    debug_mode: bool
    details_mode: bool
    busy_mode: str
    reasoning_mode: str
    quiet: bool
    conversation_history: list[dict]
    last_user_input: str = ""
    last_stop_reason: str = "complete"
    last_iterations: int = 0


def _build_fullscreen_style() -> PTStyle:
    from mlaude.skin_engine import get_fullscreen_style_overrides

    base = {
        "transcript": "bg:#181818 #F3EFD9",
        "status-bar": "bg:#151515 #B88A11",
        "input-rule": "#8A5A17",
        "prompt": "bg:#181818 #F4E8C1 bold",
        "input-shell": "bg:#181818 #F4E8C1",
        "input-area": "bg:#181818 #F4E8C1",
        "placeholder": "#8B7A55 italic",
        "completion-menu": "bg:#151515 #F3EFD9",
        "completion-menu.completion": "bg:#151515 #F3EFD9",
        "completion-menu.completion.current": "bg:#333333 #FFD447",
        "completion-menu.meta.completion": "bg:#151515 #8B7A55",
        "completion-menu.meta.completion.current": "bg:#333333 #B88A11",
    }
    base.update(get_fullscreen_style_overrides())
    return PTStyle.from_dict(base)


def _append_command_output(shell: FullscreenChatShell, text: str) -> None:
    if not text:
        return
    shell.append_blank_line()
    shell.append_text(text)
    shell.append_blank_line()


def _append_assistant_response(shell: FullscreenChatShell, response: str) -> None:
    from mlaude.skin_engine import get_active_skin

    skin = get_active_skin()
    assistant_name = skin.get_branding("assistant_name", skin.get_branding("agent_name", "mlaude"))
    assistant_icon = skin.get_branding("assistant_icon", "☠")
    shell.append_blank_line()
    shell.append_text(build_assistant_header(assistant_name, assistant_icon))
    shell.append_blank_line()
    for line in (response.splitlines() or [""]):
        shell.append_text(f"  {line}")
    shell.append_blank_line()


def _update_shell_status(
    shell: FullscreenChatShell,
    state: _InteractiveState,
    *,
    busy: bool = False,
    turn_usage: dict[str, int] | None = None,
    model_label: str | None = None,
    provider_label: str | None = None,
    api_calls: int | None = None,
    stop_reason: str | None = None,
) -> None:
    from mlaude.providers.registry import get_provider_label

    session = state.db.get_session(state.agent.session_id) or {}
    shell.set_status(
        build_status_line(
            model_label=model_label or state.agent.model,
            provider_label=provider_label or get_provider_label(state.current_provider or state.agent.provider_name),
            turn_tokens=(turn_usage or {}).get("total_tokens") if turn_usage else None,
            session_tokens=session.get("total_tokens"),
            api_calls=api_calls if api_calls is not None else state.last_iterations or None,
            busy=busy,
            stop_reason=stop_reason or state.last_stop_reason,
        )
    )


def _render_welcome(shell: FullscreenChatShell) -> None:
    from mlaude.skin_engine import get_active_skin

    skin = get_active_skin()
    agent_name = skin.get_branding("agent_name", "mlaude")
    welcome = skin.get_branding("welcome", "Welcome to mlaude! Type your message or /help for commands.")
    logo_text = skin.banner_logo or ""
    if not logo_text and agent_name == "mlaude":
        from mlaude.banner import MLAUDE_LOGO

        logo_text = MLAUDE_LOGO

    lines = build_startup_banner(
        agent_name=agent_name,
        version=VERSION,
        welcome_text=welcome,
        helper_text="Use /help for commands. Ctrl+C interrupts a running turn, then exits.",
        logo_text=logo_text,
        width=max(60, shutil.get_terminal_size((80, 24)).columns - 2),
    )
    shell.append_block(lines)


def _handle_command(
    user_input: str,
    state: _InteractiveState,
    shell: FullscreenChatShell,
) -> str | None:
    from mlaude.providers.registry import get_provider_label
    from mlaude.skin_engine import get_active_skin, set_active_skin

    canonical, args_str = resolve_command(user_input)

    if canonical == "quit":
        state.db.end_session(state.agent.session_id)
        shell.append_blank_line()
        shell.append_text(get_active_skin().get_branding("goodbye", "Goodbye!"))
        shell.exit()
        return None

    if canonical == "help":
        _append_command_output(shell, _capture_console_output(_show_help))
        return None

    if canonical == "new":
        state.conversation_history = []
        state.agent = MLaudeAgent(
            base_url=state.base_url,
            model=state.model,
            temperature=state.temperature,
            quiet_mode=state.quiet,
            provider=state.current_provider,
            session_db=state.db,
        )
        shell.append_text(build_notice_line("New session started."))
        _update_shell_status(shell, state)
        return None

    if canonical == "model":
        if args_str:
            state.model = args_str.strip()
            state.agent.model = state.model
            shell.append_text(build_notice_line(f"Model set to: {state.model}"))
        else:
            shell.append_text(build_notice_line(f"Current model: {state.agent.model}"))
        _update_shell_status(shell, state)
        return None

    if canonical == "provider":
        if args_str:
            new_provider = args_str.strip()
            state.current_provider = new_provider
            label = get_provider_label(new_provider)
            state.agent = MLaudeAgent(
                base_url=state.base_url,
                model=state.model,
                temperature=state.temperature,
                quiet_mode=state.quiet,
                provider=new_provider,
                session_db=state.db,
            )
            state.conversation_history = []
            shell.append_text(build_notice_line(f"Provider set to: {label} (new session)"))
            _update_shell_status(shell, state, provider_label=label)
        else:
            _append_command_output(shell, _capture_console_output(_show_providers))
        return None

    if canonical == "temperature":
        if args_str:
            try:
                state.temperature = float(args_str)
                state.agent.temperature = state.temperature
                shell.append_text(build_notice_line(f"Temperature set to: {state.temperature}"))
            except ValueError:
                shell.append_text(build_notice_line("Invalid temperature value.", prefix="!"))
        else:
            shell.append_text(build_notice_line(f"Current temperature: {state.agent.temperature}"))
        return None

    if canonical == "tools":
        _append_command_output(shell, _capture_console_output(_show_tools))
        return None

    if canonical == "toolsets":
        _append_command_output(shell, _capture_console_output(_show_toolsets))
        return None

    if canonical == "skills":
        _append_command_output(shell, _capture_console_output(_show_skills))
        return None

    if canonical == "sessions":
        _append_command_output(shell, _capture_console_output(lambda out: _show_sessions(state.db, out)))
        return None

    if canonical == "usage":
        session = state.db.get_session(state.agent.session_id) or {}
        shell.append_text(
            build_notice_line(
                f"Session {state.agent.session_id[:12]}… | tokens {session.get('total_tokens', 0):,} | cost ${float(session.get('total_cost', 0.0)):.4f}"
            )
        )
        return None

    if canonical == "compress":
        source_id = state.agent.session_id
        new_sid = state.db.create_continuation_session(source_id)
        state.agent.session_id = new_sid
        state.conversation_history = []
        shell.append_text(
            build_notice_line(
                f"Compressed context into continuation session {new_sid[:12]}… (parent {source_id[:12]}…)"
            )
        )
        _update_shell_status(shell, state)
        return None

    if canonical == "title":
        if args_str.strip():
            state.db.update_session_title(state.agent.session_id, args_str.strip())
            shell.append_text(build_notice_line("Session title updated."))
        else:
            session = state.db.get_session(state.agent.session_id) or {}
            shell.append_text(build_notice_line(f"Title: {session.get('title', '') or '(untitled)'}"))
        return None

    if canonical == "retry":
        if state.last_user_input:
            return state.last_user_input
        shell.append_text(build_notice_line("No prior user message to retry."))
        return None

    if canonical == "undo":
        if len(state.conversation_history) >= 2:
            state.conversation_history = state.conversation_history[:-2]
            shell.append_text(build_notice_line("Removed last conversation turn from in-memory context."))
        else:
            shell.append_text(build_notice_line("Not enough context to undo."))
        return None

    if canonical == "resume":
        sid = args_str.strip()
        if not sid:
            _append_command_output(shell, _capture_console_output(lambda out: _show_sessions(state.db, out)))
            shell.append_text(build_notice_line("Usage: /resume <session_id>"))
            return None
        full_sessions = state.db.list_sessions(limit=100)
        match = next((session for session in full_sessions if session["id"].startswith(sid)), None)
        if match:
            history = state.db.get_openai_messages(match["id"])
            state.conversation_history = [m for m in history if m.get("role") != "system"]
            state.agent.session_id = match["id"]
            shell.append_text(
                build_notice_line(
                    f"Resumed session {match['id'][:12]}… ({len(state.conversation_history)} messages)"
                )
            )
            _update_shell_status(shell, state)
        else:
            shell.append_text(build_notice_line(f"Session not found: {sid}", prefix="!"))
        return None

    if canonical == "delete":
        sid = args_str.strip()
        if not sid:
            shell.append_text(build_notice_line("Usage: /delete <session_id>"))
            return None
        full_sessions = state.db.list_sessions(limit=100)
        match = next((session for session in full_sessions if session["id"].startswith(sid)), None)
        if match:
            state.db.delete_session(match["id"])
            shell.append_text(build_notice_line(f"Deleted session {match['id'][:12]}…"))
        else:
            shell.append_text(build_notice_line(f"Session not found: {sid}", prefix="!"))
        return None

    if canonical == "search":
        query = args_str.strip()
        if not query:
            shell.append_text(build_notice_line("Usage: /search <query>"))
            return None
        results = state.db.search_sessions(query)
        if results:
            lines = [f"Search: {query}", ""]
            for result in results:
                lines.append(
                    f"{result['id'][:12]}  {result.get('updated_at', '')[:19]}  {result.get('title', '') or '(untitled)'}"
                )
            _append_command_output(shell, "\n".join(lines))
        else:
            shell.append_text(build_notice_line(f"No results for: {query}"))
        return None

    if canonical == "copy":
        if state.conversation_history:
            last_msg = next(
                (
                    message["content"]
                    for message in reversed(state.conversation_history)
                    if message.get("role") == "assistant" and message.get("content")
                ),
                None,
            )
            if last_msg:
                try:
                    import subprocess

                    proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
                    proc.communicate(last_msg.encode())
                    shell.append_text(build_notice_line("Copied last response to clipboard."))
                except Exception:
                    shell.append_text(build_notice_line("Clipboard not available.", prefix="!"))
            else:
                shell.append_text(build_notice_line("No assistant response to copy."))
        else:
            shell.append_text(build_notice_line("No conversation history."))
        return None

    if canonical == "history":
        msgs = state.db.get_messages(state.agent.session_id, limit=20)
        lines = [f"{message['role']}: {(message.get('content') or '')[:100]}" for message in msgs]
        _append_command_output(shell, "\n".join(lines) if lines else "No history.")
        return None

    if canonical == "stats":
        _append_command_output(shell, _capture_console_output(lambda out: _show_stats(state.db, out)))
        return None

    if canonical == "version":
        shell.append_text(build_notice_line(f"mlaude v{VERSION}"))
        return None

    if canonical == "debug":
        state.debug_mode = not state.debug_mode
        level = logging.DEBUG if state.debug_mode else logging.WARNING
        logging.getLogger("mlaude").setLevel(level)
        shell.append_text(build_notice_line(f"Debug: {'on' if state.debug_mode else 'off'}"))
        return None

    if canonical == "busy":
        if args_str.strip() in {"on", "off"}:
            state.busy_mode = args_str.strip()
            save_config_value("display.busy_input_mode", state.busy_mode)
        shell.append_text(build_notice_line(f"Busy input mode: {state.busy_mode}"))
        return None

    if canonical == "reasoning":
        if args_str.strip() in {"low", "medium", "high"}:
            state.reasoning_mode = args_str.strip()
        shell.append_text(build_notice_line(f"Reasoning mode: {state.reasoning_mode}"))
        return None

    if canonical == "details":
        if args_str.strip() in {"on", "off"}:
            state.details_mode = args_str.strip() == "on"
            save_config_value("display.details_mode", state.details_mode)
        shell.append_text(build_notice_line(f"Details mode: {'on' if state.details_mode else 'off'}"))
        return None

    if canonical == "system":
        if args_str:
            state.agent.system_prompt = args_str
            shell.append_text(build_notice_line("System prompt updated."))
        else:
            shell.append_text(build_notice_line(state.agent.system_prompt[:200]))
        return None

    if canonical == "skin":
        if args_str:
            skin_name = args_str.strip()
            set_active_skin(skin_name)
            save_config_value("display.skin", skin_name)
            shell.set_style(_build_fullscreen_style())
            from mlaude.skin_engine import get_active_prompt_symbol
            shell.set_prompt(get_active_prompt_symbol().strip() or ">")
            shell.append_text(build_notice_line(f"Skin set to: {skin_name}"))
        else:
            _append_command_output(shell, _capture_console_output(_show_skins))
        return None

    if canonical == "config":
        _append_command_output(
            shell,
            _capture_console_output(
                lambda out: _show_config(
                    state.model,
                    state.base_url,
                    state.temperature,
                    state.current_provider or "auto",
                    out,
                )
            ),
        )
        return None

    shell.append_text(build_notice_line(f"Unknown command: {user_input.split()[0]}", prefix="!"))
    return None


def _run_fullscreen_chat(
    *,
    state: _InteractiveState,
) -> None:
    from mlaude.skin_engine import get_active_prompt_symbol

    completer = SlashCommandCompleter()
    history_file = MLAUDE_HOME / "history"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    busy_lock = threading.Lock()
    busy_state = {"value": False}
    interrupt_count = {"value": 0}

    shell: FullscreenChatShell

    def _set_busy(value: bool) -> None:
        with busy_lock:
            busy_state["value"] = value
        shell.set_busy(value, "Working..." if value else "")

    def _is_busy() -> bool:
        with busy_lock:
            return busy_state["value"]

    def _handle_interrupt() -> bool:
        if _is_busy():
            interrupt_count["value"] += 1
            if interrupt_count["value"] >= 2:
                return False
            state.agent.request_interrupt()
            shell.append_text(build_notice_line("Interrupting… (Ctrl+C again to quit)", prefix="!"))
            return True
        return False

    def _handle_exit() -> None:
        state.db.end_session(state.agent.session_id)

    def _start_agent_turn(text: str) -> None:
        if _is_busy():
            return

        interrupt_count["value"] = 0
        state.agent._interrupt_requested = False
        state.last_user_input = text
        state.agent.reasoning_effort = state.reasoning_mode
        state.agent.on_approval_request = lambda tool, args: shell.prompt_for_approval(tool)
        state.agent.on_tool_start = lambda name, args: shell.append_text(
            build_notice_line(f"{name}({', '.join(f'{k}={repr(v)[:50]}' for k, v in list(args.items())[:3])})")
        )
        state.agent.on_tool_end = lambda name, result: shell.append_text(
            build_notice_line(f"{name} → {result[:160].replace(chr(10), ' ')}")
        )

        shell.append_blank_line()
        shell.append_text(f"{get_active_prompt_symbol().strip()} {text}")
        _set_busy(True)
        _update_shell_status(shell, state, busy=True)

        def _worker() -> None:
            try:
                result = state.agent.run_conversation(
                    user_message=text,
                    conversation_history=state.conversation_history,
                )
            except Exception as exc:
                shell.append_blank_line()
                shell.append_text(build_notice_line(f"Error: {exc}", prefix="!"))
                state.last_stop_reason = f"error: {exc}"
                state.last_iterations = 0
                _set_busy(False)
                _update_shell_status(shell, state, busy=False, stop_reason=state.last_stop_reason)
                return

            final = result.get("final_response", "")
            if final:
                _append_assistant_response(shell, final)

            if len(state.conversation_history) == 0 and final:
                state.db.update_session_title(state.agent.session_id, text[:60])

            state.conversation_history = [m for m in result.get("messages", []) if m.get("role") != "system"]
            state.last_stop_reason = result.get("stop_reason", "complete")
            state.last_iterations = result.get("iterations_used", 0)

            if state.details_mode:
                shell.append_text(
                    build_notice_line(
                        f"reasoning={state.reasoning_mode} route={result.get('route', '')} stop={state.last_stop_reason}"
                    )
                )

            _set_busy(False)
            _update_shell_status(
                shell,
                state,
                busy=False,
                turn_usage=result.get("turn_usage"),
                model_label=result.get("model_label"),
                provider_label=result.get("provider_label"),
                api_calls=result.get("iterations_used"),
                stop_reason=state.last_stop_reason,
            )

        threading.Thread(target=_worker, daemon=True).start()

    def _submit(text: str) -> None:
        if text.startswith("/"):
            replacement = _handle_command(text, state, shell)
            if replacement:
                _start_agent_turn(replacement)
            return
        _start_agent_turn(text)

    shell = FullscreenChatShell(
        history_file=str(history_file),
        completer=completer,
        style=_build_fullscreen_style(),
        on_submit=_submit,
        on_interrupt=_handle_interrupt,
        on_exit=_handle_exit,
        initial_prompt=get_active_prompt_symbol().strip() or ">",
    )
    _render_welcome(shell)
    _update_shell_status(shell, state)
    shell.run()


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    model: str = typer.Option(DEFAULT_CHAT_MODEL, "--model", "-m", help="Model to use"),
    base_url: str = typer.Option(LLM_BASE_URL, "--base-url", help="LLM API base URL"),
    temperature: float = typer.Option(DEFAULT_TEMPERATURE, "--temperature", "-t", help="Temperature"),
    one_shot: str = typer.Option(None, "--message", "-M", help="One-shot message (non-interactive)"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress status output"),
    session: str = typer.Option(None, "--session", "-s", help="Resume a session by ID"),
    resume: str = typer.Option(None, "--resume", "-r", help="Resume a session by ID"),
    continue_last: bool = typer.Option(False, "--continue", "-c", help="Continue most recent session"),
    tui: bool = typer.Option(False, "--tui", help="Launch fullscreen TUI (default interactive mode)"),
    tui_dev: bool = typer.Option(False, "--tui-dev", help="Launch fullscreen TUI dev path"),
    yolo: bool = typer.Option(False, "--yolo", help="Disable approval prompts for risky tools"),
    provider: str = typer.Option(None, "--provider", "-p", help="Provider override"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
    skin: str = typer.Option(None, "--skin", help="Skin theme to use"),
):
    """Start the mlaude interactive agent."""
    if ctx.invoked_subcommand is not None:
        return

    if debug:
        logging.basicConfig(level=logging.DEBUG)

    ensure_app_dirs()
    safety_policy.set_yolo(yolo)

    # Load config and initialize skin
    config = load_config()
    from mlaude.skin_engine import init_skin_from_config, set_active_skin
    if skin:
        set_active_skin(skin)
    else:
        init_skin_from_config(config)

    # Start background update check
    prefetch_update_check()

    db = SessionDB()
    resume_id = resume or session
    if continue_last and not resume_id:
        recent = db.list_sessions(limit=1)
        if recent:
            resume_id = recent[0]["id"]

    # One-shot mode
    if one_shot:
        discover_tools()
        agent = MLaudeAgent(
            base_url=base_url,
            model=model,
            temperature=temperature,
            quiet_mode=quiet,
            provider=provider,
            session_db=db,
        )
        conversation_history: list[dict] = []
        if resume_id:
            resolved = db.resolve_session_id(resume_id) or resume_id
            history = db.get_openai_messages(resolved)
            if history:
                conversation_history = [m for m in history if m.get("role") != "system"]
                agent.session_id = resolved
                console.print(f"[dim]Resumed session {resolved[:12]}… ({len(history)} messages)[/dim]")
            else:
                console.print(f"[dim]Session {resume_id} not found, starting new.[/dim]")
        spinner = Spinner()
        spinner.start("thinking")
        result = agent.run_conversation(one_shot, conversation_history=conversation_history)
        spinner.stop()
        response = result.get("final_response", "")
        if response:
            console.print(Markdown(response))
        if str(result.get("stop_reason", "")).startswith("error:"):
            raise typer.Exit(code=1)
        return

    _ensure_interactive_tty()
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    _launch_tui(
        cwd=os.getcwd(),
        resume_id=resume_id,
        provider=provider,
        model=model,
        base_url=base_url,
        temperature=temperature,
        yolo=yolo,
        skin=skin,
        tui_dev=tui_dev,
    )


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(7474, "--port", "-p", help="Port to listen on"),
):
    """Start the gateway webhook server (WhatsApp/Telegram/Email)."""
    import uvicorn

    console.print(
        Panel(
            f"[bold bright_yellow]mlaude gateway[/bold bright_yellow]\n\n"
            f"  Listening: [bold]http://{host}:{port}[/bold]\n"
            f"  [dim]Stop with Ctrl+C[/dim]",
            border_style="bright_yellow",
        )
    )

    uvicorn.run(
        "mlaude.server:app",
        host=host,
        port=port,
        log_level="warning",
    )


@app.command()
def gateway(
    host: str = typer.Option("0.0.0.0", "--host", help="Host to bind to"),
    port: int = typer.Option(7474, "--port", help="Port"),
    config: str = typer.Option(None, "--config", help="Gateway config YAML"),
):
    """Start the full gateway with platform adapters."""
    import yaml
    import uvicorn

    gateway_config: dict = {}
    config_path = config or str(MLAUDE_HOME / "config.yaml")

    try:
        from pathlib import Path
        p = Path(config_path)
        if p.exists():
            gateway_config = yaml.safe_load(p.read_text()) or {}
    except Exception as e:
        console.print(f"[yellow]Warning: Could not load config: {e}[/yellow]")

    # Setup orchestrator
    from mlaude.gateway.run import GatewayOrchestrator
    from mlaude.server import set_orchestrator

    orchestrator = GatewayOrchestrator(gateway_config)
    set_orchestrator(orchestrator)

    platforms = gateway_config.get("platforms", {})
    enabled = [k for k, v in platforms.items() if v.get("enabled")]

    console.print(
        Panel(
            f"[bold bright_yellow]mlaude gateway[/bold bright_yellow]\n\n"
            f"  Listening: [bold]http://{host}:{port}[/bold]\n"
            f"  Platforms: [bold]{', '.join(enabled) or 'none configured'}[/bold]\n"
            f"  Config:    [dim]{config_path}[/dim]\n\n"
            f"  [dim]Stop with Ctrl+C[/dim]",
            border_style="bright_yellow",
        )
    )

    uvicorn.run(
        "mlaude.server:app",
        host=host,
        port=port,
        log_level="info",
    )
