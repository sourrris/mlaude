"""CLI entry point — Hermes-style interactive agent.

Full interactive CLI with Rich panels, animated spinners, slash command
autocomplete, session management, and tool activity display.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

import typer
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import InMemoryHistory
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from mlaude.agent import MLaudeAgent
from mlaude.commands import (
    COMMANDS,
    COMMANDS_BY_CATEGORY,
    resolve_command,
)
from mlaude.display import Spinner, format_tool_start, format_tool_end, get_tool_emoji
from mlaude.model_tools import discover_tools
from mlaude.settings import (
    DEFAULT_CHAT_MODEL,
    DEFAULT_TEMPERATURE,
    LLM_BASE_URL,
    MLAUDE_HOME,
    ensure_app_dirs,
)
from mlaude.state import SessionDB

app = typer.Typer(name="mlaude", invoke_without_command=True)
console = Console()
logger = logging.getLogger(__name__)

VERSION = "0.3.0-dev"


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------


def _print_banner(model: str, base_url: str, tool_count: int) -> None:
    console.print()
    console.print(
        Panel(
            Text.from_markup(
                f"[bold bright_yellow]mlaude[/bold bright_yellow]  ·  [dim]local AI agent[/dim]\n\n"
                f"  [bold]Model[/bold]     [bright_cyan]{model}[/bright_cyan]\n"
                f"  [bold]Runtime[/bold]   [dim]{base_url}[/dim]\n"
                f"  [bold]Tools[/bold]     [dim]{tool_count} loaded[/dim]\n"
                f"  [bold]Home[/bold]      [dim]{MLAUDE_HOME}[/dim]\n\n"
                f"  [dim italic]Type a message or /help for commands · Ctrl+C to interrupt[/dim italic]"
            ),
            border_style="bright_yellow",
            title=f"[dim]v{VERSION}[/dim]",
            title_align="right",
            padding=(0, 2),
        )
    )
    console.print()


# ---------------------------------------------------------------------------
# Slash command handlers
# ---------------------------------------------------------------------------


def _show_help() -> None:
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


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    model: str = typer.Option(DEFAULT_CHAT_MODEL, "--model", "-m", help="Model to use"),
    base_url: str = typer.Option(LLM_BASE_URL, "--base-url", help="LLM API base URL"),
    temperature: float = typer.Option(DEFAULT_TEMPERATURE, "--temperature", "-t", help="Temperature"),
    one_shot: str = typer.Option(None, "--message", "-c", help="One-shot message (non-interactive)"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress status output"),
    session: str = typer.Option(None, "--session", "-s", help="Resume a session by ID"),
    provider: str = typer.Option(None, "--provider", "-p", help="Provider override"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
):
    """Start the mlaude interactive agent."""
    if ctx.invoked_subcommand is not None:
        return

    if debug:
        logging.basicConfig(level=logging.DEBUG)

    ensure_app_dirs()
    db = SessionDB()

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
    if session:
        history = db.get_openai_messages(session)
        if history:
            conversation_history = [m for m in history if m.get("role") != "system"]
            agent.session_id = session
            console.print(f"[dim]Resumed session {session[:12]}… ({len(history)} messages)[/dim]")
        else:
            console.print(f"[dim]Session {session} not found, starting new.[/dim]")

    # Create DB session
    if not session:
        db.create_session(
            session_id=agent.session_id,
            platform="cli",
            model=model,
        )

    # One-shot mode
    if one_shot:
        spinner = Spinner()
        spinner.start("thinking")
        response = agent.chat(one_shot)
        spinner.stop()
        if response:
            console.print(Markdown(response))
        return

    # Interactive mode
    _print_banner(model, base_url, tool_count)

    # Setup prompt_toolkit
    cmd_names = ["/" + name for name in COMMANDS.keys()]
    completer = WordCompleter(cmd_names, sentence=True)
    prompt_session: PromptSession = PromptSession(
        completer=completer,
        history=InMemoryHistory(),
    )

    # Interrupt handling
    _interrupt_count = 0

    def _sigint_handler(sig, frame):
        nonlocal _interrupt_count
        _interrupt_count += 1
        if _interrupt_count >= 2:
            console.print("\n[dim]Goodbye.[/dim]")
            sys.exit(0)
        agent.request_interrupt()
        console.print("\n[dim]Interrupting… (Ctrl+C again to quit)[/dim]")

    signal.signal(signal.SIGINT, _sigint_handler)

    debug_mode = debug

    while True:
        try:
            user_input = prompt_session.prompt(
                [("class:prompt", "❯ ")],
                style=None,
            ).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        if not user_input:
            continue

        _interrupt_count = 0

        # Slash commands
        if user_input.startswith("/"):
            canonical, args_str = resolve_command(user_input)

            if canonical == "quit":
                db.end_session(agent.session_id)
                console.print("[dim]Goodbye.[/dim]")
                break

            elif canonical == "help":
                _show_help()
                continue

            elif canonical == "new":
                conversation_history = []
                agent = MLaudeAgent(
                    base_url=base_url, model=model, temperature=temperature,
                    quiet_mode=quiet, provider=provider,
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

            elif canonical == "resume":
                sid = args_str.strip()
                if not sid:
                    _show_sessions(db)
                    console.print("[dim]Usage: /resume <session_id>[/dim]")
                    continue
                # Find matching session
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

            elif canonical == "system":
                if args_str:
                    agent.system_prompt = args_str
                    console.print("[dim]System prompt updated.[/dim]")
                else:
                    console.print(f"[dim]{agent.system_prompt[:200]}[/dim]")
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
            console.print()
            console.print(
                Panel(
                    Markdown(final),
                    border_style="bright_black",
                    title="[dim bright_yellow]mlaude[/dim bright_yellow]",
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
