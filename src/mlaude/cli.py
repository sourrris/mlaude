"""CLI entry point — Hermes-style interactive agent.

Full interactive CLI with Rich panels, animated spinners, slash command
autocomplete, session management, skin engine, and tool activity display.
Faithful port of the Hermes Agent CLI experience.
"""

from __future__ import annotations

import logging
import os
import json
import signal
import sys

import typer
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style as PTStyle
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from mlaude.agent import MLaudeAgent
from mlaude.banner import VERSION, build_welcome_banner, prefetch_update_check
from mlaude.commands import (
    COMMANDS_BY_CATEGORY,
    resolve_command,
    SlashCommandCompleter,
    SlashCommandAutoSuggest,
)
from mlaude.display import Spinner, format_tool_start, format_tool_end, get_tool_emoji
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

app = typer.Typer(name="mlaude", invoke_without_command=True)
console = Console()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Slash command handlers
# ---------------------------------------------------------------------------


def _show_help() -> None:
    from mlaude.skin_engine import get_active_help_header
    header = get_active_help_header()
    console.print(f"\n  [bold]{header}[/bold]\n")

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
        console.print(table)
        console.print()


def _show_tools() -> None:
    from mlaude.tools.registry import registry
    tools = registry.get_all()
    if not tools:
        console.print("[dim]No tools loaded.[/dim]")
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

    console.print(table)


def _show_toolsets() -> None:
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

    console.print(table)


def _show_skills() -> None:
    from mlaude.settings import SKILLS_DIR

    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    skill_files = sorted(SKILLS_DIR.glob("**/*.md"))

    if not skill_files:
        console.print(
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

    console.print(table)
    console.print(f"  [dim]Skills directory: {SKILLS_DIR}[/dim]")


def _show_sessions(db: SessionDB) -> None:
    sessions = db.list_sessions(limit=15)
    if not sessions:
        console.print("[dim]No sessions yet.[/dim]")
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

    console.print(table)


def _show_stats(db: SessionDB) -> None:
    stats = db.get_stats()
    console.print(
        f"  [bold]Sessions:[/bold] {stats['sessions']}  "
        f"[bold]Messages:[/bold] {stats['messages']}  "
        f"[bold]Tokens:[/bold] {stats['total_tokens']:,}"
    )


def _show_skins() -> None:
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

    console.print(table)


def _show_providers() -> None:
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

    console.print(table)


def _show_config(model: str, base_url: str, temperature: float, provider: str) -> None:
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

    console.print(table)


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
    tui: bool = typer.Option(False, "--tui", help="Launch TUI (fallback to classic CLI if unavailable)"),
    tui_dev: bool = typer.Option(False, "--tui-dev", help="Launch TUI in dev mode (fallback if unavailable)"),
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
    if tui or tui_dev:
        from mlaude.tui_gateway.launcher import can_launch_tui
        ok, reason = can_launch_tui()
        if not ok:
            console.print(f"[dim]TUI unavailable ({reason}); falling back to classic CLI.[/dim]")
        else:
            console.print("[dim]TUI runtime scaffold is present, but frontend is not bundled yet; using classic CLI.[/dim]")

    # Discover tools
    tool_count = discover_tools()

    # Create agent
    agent = MLaudeAgent(
        base_url=base_url,
        model=model,
        temperature=temperature,
        quiet_mode=quiet,
        provider=provider,
    )

    # Resume session if specified
    conversation_history: list[dict] = []
    resume_id = resume or session
    if continue_last and not resume_id:
        recent = db.list_sessions(limit=1)
        if recent:
            resume_id = recent[0]["id"]

    if resume_id:
        resolved = db.resolve_session_id(resume_id) or resume_id
        history = db.get_openai_messages(resolved)
        if history:
            conversation_history = [m for m in history if m.get("role") != "system"]
            agent.session_id = resolved
            console.print(f"[dim]Resumed session {resolved[:12]}… ({len(history)} messages)[/dim]")
        else:
            console.print(f"[dim]Session {resume_id} not found, starting new.[/dim]")

    # Create DB session
    if not resume_id:
        db.create_session(
            session_id=agent.session_id,
            platform="cli",
            model=model,
        )

    # One-shot mode
    if one_shot:
        spinner = Spinner()
        spinner.start("thinking")
        result = agent.run_conversation(one_shot)
        spinner.stop()
        response = result.get("final_response", "")
        if response:
            console.print(Markdown(response))
        if str(result.get("stop_reason", "")).startswith("error:"):
            raise typer.Exit(code=1)
        return

    # Interactive mode — print banner
    build_welcome_banner(
        console=console,
        model=model,
        cwd=os.getcwd(),
        session_id=agent.session_id,
        tool_count=tool_count,
    )

    # Welcome message
    from mlaude.skin_engine import get_active_skin
    welcome = get_active_skin().get_branding("welcome", "")
    if welcome:
        console.print(f"\n  [dim]{welcome}[/dim]\n")

    # Setup prompt_toolkit with rich completer
    from mlaude.skin_engine import get_active_prompt_symbol, get_prompt_toolkit_style_overrides
    from prompt_toolkit import PromptSession

    _completer = SlashCommandCompleter()
    _history_file = MLAUDE_HOME / "history"
    _history_file.parent.mkdir(parents=True, exist_ok=True)

    # Build skin-aware style
    _tui_style_base = {
        'input-area': '#FFF8DC',
        'placeholder': '#555555 italic',
        'prompt': '#FFF8DC',
        'prompt-working': '#888888 italic',
        'completion-menu': 'bg:#1a1a2e #FFF8DC',
        'completion-menu.completion': 'bg:#1a1a2e #FFF8DC',
        'completion-menu.completion.current': 'bg:#333355 #FFD700',
        'completion-menu.meta.completion': 'bg:#1a1a2e #888888',
        'completion-menu.meta.completion.current': 'bg:#333355 #FFBF00',
    }
    _tui_style_base.update(get_prompt_toolkit_style_overrides())
    _pt_style = PTStyle.from_dict(_tui_style_base)

    prompt_session: PromptSession = PromptSession(
        completer=_completer,
        complete_while_typing=True,
        history=FileHistory(str(_history_file)),
        auto_suggest=SlashCommandAutoSuggest(
            history_suggest=AutoSuggestFromHistory(),
            completer=_completer,
        ),
        style=_pt_style,
    )

    # Interrupt handling
    _interrupt_count = 0

    def _sigint_handler(sig, frame):
        nonlocal _interrupt_count
        _interrupt_count += 1
        if _interrupt_count >= 2:
            goodbye = get_active_skin().get_branding("goodbye", "Goodbye!")
            console.print(f"\n[dim]{goodbye}[/dim]")
            sys.exit(0)
        agent.request_interrupt()
        console.print("\n[dim]Interrupting… (Ctrl+C again to quit)[/dim]")

    signal.signal(signal.SIGINT, _sigint_handler)

    debug_mode = debug
    current_provider = provider
    details_mode = bool(config.get("display", {}).get("details_mode", False))
    busy_mode = str(config.get("display", {}).get("busy_input_mode", "off"))
    reasoning_mode = "medium"
    last_user_input = ""

    while True:
        try:
            prompt_sym = get_active_prompt_symbol()
            user_input = prompt_session.prompt(
                [("class:prompt", prompt_sym)],
            ).strip()
        except (EOFError, KeyboardInterrupt):
            goodbye = get_active_skin().get_branding("goodbye", "Goodbye!")
            console.print(f"\n[dim]{goodbye}[/dim]")
            break

        if not user_input:
            continue

        _interrupt_count = 0

        # Slash commands
        if user_input.startswith("/"):
            canonical, args_str = resolve_command(user_input)

            if canonical == "quit":
                db.end_session(agent.session_id)
                goodbye = get_active_skin().get_branding("goodbye", "Goodbye!")
                console.print(f"[dim]{goodbye}[/dim]")
                break

            elif canonical == "help":
                _show_help()
                continue

            elif canonical == "new":
                conversation_history = []
                agent = MLaudeAgent(
                    base_url=base_url, model=model, temperature=temperature,
                    quiet_mode=quiet, provider=current_provider,
                )
                db.create_session(
                    session_id=agent.session_id, platform="cli", model=model,
                )
                console.print("[dim]New session started.[/dim]")
                continue

            elif canonical == "model":
                if args_str:
                    model = args_str.strip()
                    agent.model = model
                    console.print(f"[dim]Model set to: {model}[/dim]")
                else:
                    console.print(f"[dim]Current model: {agent.model}[/dim]")
                continue

            elif canonical == "provider":
                if args_str:
                    new_provider = args_str.strip()
                    current_provider = new_provider
                    from mlaude.providers.registry import get_provider_label
                    label = get_provider_label(new_provider)
                    # Recreate agent with new provider
                    agent = MLaudeAgent(
                        base_url=base_url, model=model, temperature=temperature,
                        quiet_mode=quiet, provider=new_provider,
                    )
                    agent.session_id = db.create_session(
                        platform="cli", model=model,
                    )
                    conversation_history = []
                    console.print(f"[dim]Provider set to: {label} (new session)[/dim]")
                else:
                    _show_providers()
                continue

            elif canonical == "temperature":
                if args_str:
                    try:
                        temperature = float(args_str)
                        agent.temperature = temperature
                        console.print(f"[dim]Temperature set to: {temperature}[/dim]")
                    except ValueError:
                        console.print("[red]Invalid temperature value.[/red]")
                else:
                    console.print(f"[dim]Current temperature: {agent.temperature}[/dim]")
                continue

            elif canonical == "tools":
                _show_tools()
                continue

            elif canonical == "toolsets":
                _show_toolsets()
                continue

            elif canonical == "skills":
                _show_skills()
                continue

            elif canonical == "sessions":
                _show_sessions(db)
                continue
            elif canonical == "usage":
                s = db.get_session(agent.session_id) or {}
                console.print(
                    f"  [bold]Session:[/bold] {agent.session_id[:12]}…  "
                    f"[bold]Tokens:[/bold] {s.get('total_tokens', 0):,}  "
                    f"[bold]Cost:[/bold] ${float(s.get('total_cost', 0.0)):.4f}"
                )
                continue
            elif canonical == "compress":
                source_id = agent.session_id
                new_sid = db.create_continuation_session(source_id)
                agent.session_id = new_sid
                conversation_history = []
                console.print(
                    f"[dim]Compressed context into new continuation session {new_sid[:12]}… "
                    f"(parent {source_id[:12]}…)[/dim]"
                )
                continue
            elif canonical == "title":
                if args_str.strip():
                    db.update_session_title(agent.session_id, args_str.strip())
                    console.print("[dim]Session title updated.[/dim]")
                else:
                    s = db.get_session(agent.session_id) or {}
                    console.print(f"[dim]Title: {s.get('title', '') or '(untitled)'}[/dim]")
                continue
            elif canonical == "retry":
                if last_user_input:
                    user_input = last_user_input
                else:
                    console.print("[dim]No prior user message to retry.[/dim]")
                    continue
            elif canonical == "undo":
                if len(conversation_history) >= 2:
                    conversation_history = conversation_history[:-2]
                    console.print("[dim]Removed last conversation turn from in-memory context.[/dim]")
                else:
                    console.print("[dim]Not enough context to undo.[/dim]")
                continue

            elif canonical == "resume":
                sid = args_str.strip()
                if not sid:
                    _show_sessions(db)
                    console.print("[dim]Usage: /resume <session_id>[/dim]")
                    continue
                full_sessions = db.list_sessions(limit=100)
                match = None
                for s in full_sessions:
                    if s["id"].startswith(sid):
                        match = s
                        break
                if match:
                    history = db.get_openai_messages(match["id"])
                    conversation_history = [m for m in history if m.get("role") != "system"]
                    agent.session_id = match["id"]
                    console.print(
                        f"[dim]Resumed session {match['id'][:12]}… "
                        f"({len(conversation_history)} messages)[/dim]"
                    )
                else:
                    console.print(f"[dim]Session not found: {sid}[/dim]")
                continue

            elif canonical == "delete":
                sid = args_str.strip()
                if not sid:
                    console.print("[dim]Usage: /delete <session_id>[/dim]")
                    continue
                full_sessions = db.list_sessions(limit=100)
                match = None
                for s in full_sessions:
                    if s["id"].startswith(sid):
                        match = s
                        break
                if match:
                    db.delete_session(match["id"])
                    console.print(f"[dim]Deleted session {match['id'][:12]}…[/dim]")
                else:
                    console.print(f"[dim]Session not found: {sid}[/dim]")
                continue

            elif canonical == "search":
                query = args_str.strip()
                if not query:
                    console.print("[dim]Usage: /search <query>[/dim]")
                    continue
                results = db.search_sessions(query)
                if results:
                    table = Table(title=f"[bold]Search: {query}[/bold]", border_style="dim")
                    table.add_column("ID", style="dim", max_width=12)
                    table.add_column("Title")
                    table.add_column("Updated", style="dim")
                    for s in results:
                        table.add_row(s["id"][:12], s.get("title", ""), s.get("updated_at", "")[:19])
                    console.print(table)
                else:
                    console.print(f"[dim]No results for: {query}[/dim]")
                continue

            elif canonical == "copy":
                # Copy last assistant response to clipboard
                if conversation_history:
                    last_msg = None
                    for m in reversed(conversation_history):
                        if m.get("role") == "assistant" and m.get("content"):
                            last_msg = m["content"]
                            break
                    if last_msg:
                        try:
                            import subprocess
                            proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
                            proc.communicate(last_msg.encode())
                            console.print("[dim]Copied last response to clipboard.[/dim]")
                        except Exception:
                            console.print("[dim]Clipboard not available.[/dim]")
                    else:
                        console.print("[dim]No assistant response to copy.[/dim]")
                else:
                    console.print("[dim]No conversation history.[/dim]")
                continue

            elif canonical == "history":
                msgs = db.get_messages(agent.session_id, limit=20)
                for m in msgs:
                    role = m["role"]
                    content = (m.get("content") or "")[:100]
                    console.print(f"  [bold]{role}[/bold]: {content}")
                continue

            elif canonical == "stats":
                _show_stats(db)
                continue

            elif canonical == "version":
                console.print(f"[dim]mlaude v{VERSION}[/dim]")
                continue

            elif canonical == "debug":
                debug_mode = not debug_mode
                level = logging.DEBUG if debug_mode else logging.WARNING
                logging.getLogger("mlaude").setLevel(level)
                console.print(f"[dim]Debug: {'on' if debug_mode else 'off'}[/dim]")
                continue
            elif canonical == "busy":
                if args_str.strip() in {"on", "off"}:
                    busy_mode = args_str.strip()
                    save_config_value("display.busy_input_mode", busy_mode)
                console.print(f"[dim]Busy input mode: {busy_mode}[/dim]")
                continue
            elif canonical == "reasoning":
                if args_str.strip() in {"low", "medium", "high"}:
                    reasoning_mode = args_str.strip()
                console.print(f"[dim]Reasoning mode: {reasoning_mode}[/dim]")
                continue
            elif canonical == "details":
                if args_str.strip() in {"on", "off"}:
                    details_mode = args_str.strip() == "on"
                    save_config_value("display.details_mode", details_mode)
                console.print(f"[dim]Details mode: {'on' if details_mode else 'off'}[/dim]")
                continue

            elif canonical == "system":
                if args_str:
                    agent.system_prompt = args_str
                    console.print("[dim]System prompt updated.[/dim]")
                else:
                    console.print(f"[dim]{agent.system_prompt[:200]}[/dim]")
                continue

            elif canonical == "skin":
                if args_str:
                    skin_name = args_str.strip()
                    set_active_skin(skin_name)
                    save_config_value("display.skin", skin_name)
                    console.print(f"[dim]Skin set to: {skin_name}[/dim]")
                else:
                    _show_skins()
                continue

            elif canonical == "config":
                _show_config(model, base_url, temperature, current_provider or "auto")
                continue

            else:
                console.print(f"[dim]Unknown command: {user_input.split()[0]}[/dim]")
                continue

        # Agent interaction
        agent._interrupt_requested = False
        spinner = Spinner()

        def on_tool_start(name: str, args: dict) -> None:
            spinner.stop()
            console.print(format_tool_start(name, args))
            spinner.start(f"{name}")

        def on_tool_end(name: str, result: str) -> None:
            spinner.stop()
            console.print(format_tool_end(name, result))
            spinner.start()

        agent.on_tool_start = on_tool_start
        agent.on_tool_end = on_tool_end

        spinner.start()
        last_user_input = user_input

        try:
            result = agent.run_conversation(
                user_message=user_input,
                conversation_history=conversation_history,
            )
        except Exception as e:
            spinner.stop()
            console.print(f"[red]Error: {e}[/red]")
            continue

        spinner.stop()

        final = result.get("final_response", "")
        if final:
            # Skin-aware response panel
            from mlaude.skin_engine import get_active_skin
            skin = get_active_skin()
            response_label = skin.get_branding("response_label", " 💀 mlaude ")
            response_border = skin.get_color("response_border", "#FFD700")

            console.print()
            if details_mode:
                console.print(f"[dim]reasoning={reasoning_mode} busy={busy_mode}[/dim]")
            console.print(
                Panel(
                    Markdown(final),
                    border_style=response_border,
                    title=f"[dim]{response_label}[/dim]",
                    title_align="left",
                    padding=(1, 2),
                )
            )
            console.print()

        # Persist messages
        db.add_message(
            session_id=agent.session_id,
            role="user",
            content=user_input,
        )
        if final:
            db.add_message(
                session_id=agent.session_id,
                role="assistant",
                content=final,
            )
        # Retry once with explicit approval for blocked risky tools.
        if not final:
            msgs = result.get("messages", [])
            blocked = None
            for m in reversed(msgs):
                if m.get("role") == "tool":
                    try:
                        payload = json.loads(m.get("content") or "{}")
                    except Exception:
                        payload = {}
                    if payload.get("error") == "approval_required":
                        blocked = payload
                        break
            if blocked:
                tool = blocked.get("tool", "tool")
                console.print(f"[yellow]Approval required for {tool}.[/yellow] Run once? [y/N]")
                try:
                    resp = prompt_session.prompt([("class:prompt", "approve> ")]).strip().lower()
                except Exception:
                    resp = "n"
                if resp in {"y", "yes"}:
                    from mlaude.tools.registry import registry
                    manual = registry.dispatch(
                        tool,
                        blocked.get("args", {}),
                        task_id=agent.session_id,
                        approval_granted=True,
                        enforce_safety=True,
                    )
                    console.print(format_tool_end(tool, manual))

        # Auto-title on first user message
        if len(conversation_history) == 0 and final:
            title = user_input[:60]
            db.update_session_title(agent.session_id, title)

        # Update conversation history
        conversation_history = [
            m for m in result.get("messages", [])
            if m.get("role") != "system"
        ]

        # Show stats
        iters = result.get("iterations_used", 0)
        reason = result.get("stop_reason", "")
        if not quiet and iters > 0:
            console.print(
                f"  [dim]({iters} API call{'s' if iters != 1 else ''}"
                f"{f' · {reason}' if reason != 'complete' else ''})[/dim]"
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
