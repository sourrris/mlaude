"""Welcome banner, ASCII art, and update check for the CLI.
"""

import json
import logging
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

logger = logging.getLogger(__name__)

VERSION = "0.3.0-dev"


# =========================================================================
# Skin-aware color helpers
# =========================================================================

def _skin_color(key: str, fallback: str) -> str:
    try:
        from mlaude.skin_engine import get_active_skin
        return get_active_skin().get_color(key, fallback)
    except Exception:
        return fallback


def _skin_branding(key: str, fallback: str) -> str:
    try:
        from mlaude.skin_engine import get_active_skin
        return get_active_skin().get_branding(key, fallback)
    except Exception:
        return fallback


# =========================================================================
# ASCII Art & Branding
# =========================================================================

MLAUDE_LOGO = """[bold #FFD700]███╗   ███╗██╗      █████╗ ██╗   ██╗██████╗ ███████╗[/]
[bold #FFD700]████╗ ████║██║     ██╔══██╗██║   ██║██╔══██╗██╔════╝[/]
[#FFBF00]██╔████╔██║██║     ███████║██║   ██║██║  ██║█████╗[/]
[#FFBF00]██║╚██╔╝██║██║     ██╔══██║██║   ██║██║  ██║██╔══╝[/]
[#CD7F32]██║ ╚═╝ ██║███████╗██║  ██║╚██████╔╝██████╔╝███████╗[/]
[#CD7F32]╚═╝     ╚═╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝[/]"""

MLAUDE_HERO = """[#CD7F32]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣀⡀⠀⣀⣀⠀⢀⣀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀[/]
    [#CD7F32]⠀⠀⠀⠀⠀⠀⢀⣠⣴⣾⣿⣿⣇⠸⣿⣿⠇⣸⣿⣿⣷⣦⣄⡀⠀⠀⠀⠀⠀⠀[/]
    [#FFBF00]⠀⢀⣠⣴⣶⠿⠋⣩⡿⣿⡿⠻⣿⡇⢠⡄⢸⣿⠟⢿⣿⢿⣍⠙⠿⣶⣦⣄⡀⠀[/]
    [#FFBF00]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠉⠻⢿⣿⣦⡉⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀[/]
    [#FFBF00]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⢷⣦⣈⠛⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀[/]
    [#CD7F32]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢠⣴⠦⠈⠙⠿⣦⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀[/]
    [#CD7F32]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠸⣿⣤⡈⠁⢤⣿⠇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀[/]
    [#B8860B]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠛⠷⠄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀[/]
    [#B8860B]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣀⠑⢶⣄⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀[/]
    [#B8860B]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⠁⢰⡆⠈⡿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀[/]
    [#B8860B]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠳⠈⣡⠞⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀[/]
    [#B8860B]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀[/]"""


# =========================================================================
# Skills scanning
# =========================================================================

def get_available_skills() -> Dict[str, List[str]]:
    """Return skills grouped by category."""
    from mlaude.settings import SKILLS_DIR
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    skills_by_category: Dict[str, List[str]] = {}
    for f in sorted(SKILLS_DIR.glob("**/*.md")):
        rel = f.relative_to(SKILLS_DIR)
        parts = rel.parts
        category = parts[0] if len(parts) > 1 else "general"
        name = rel.stem
        skills_by_category.setdefault(category, []).append(name)
    return skills_by_category


# =========================================================================
# Update check
# =========================================================================

_UPDATE_CHECK_CACHE_SECONDS = 6 * 3600
_update_result: Optional[int] = None
_update_check_done = threading.Event()


def check_for_updates() -> Optional[int]:
    """Check how many commits behind origin/main the local repo is."""
    from mlaude.settings import PROJECT_ROOT
    repo_dir = PROJECT_ROOT
    if not (repo_dir / ".git").exists():
        return None

    cache_file = Path.home() / ".mlaude" / ".update_check"
    now = time.time()
    try:
        if cache_file.exists():
            cached = json.loads(cache_file.read_text())
            if now - cached.get("ts", 0) < _UPDATE_CHECK_CACHE_SECONDS:
                return cached.get("behind")
    except Exception:
        pass

    try:
        subprocess.run(
            ["git", "fetch", "origin", "--quiet"],
            capture_output=True, timeout=10, cwd=str(repo_dir),
        )
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD..origin/main"],
            capture_output=True, text=True, timeout=5, cwd=str(repo_dir),
        )
        behind = int(result.stdout.strip()) if result.returncode == 0 else None
    except Exception:
        behind = None

    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps({"ts": now, "behind": behind}))
    except Exception:
        pass

    return behind


def prefetch_update_check():
    def _run():
        global _update_result
        _update_result = check_for_updates()
        _update_check_done.set()
    t = threading.Thread(target=_run, daemon=True)
    t.start()


def get_update_result(timeout: float = 0.5) -> Optional[int]:
    _update_check_done.wait(timeout=timeout)
    return _update_result


# =========================================================================
# Context length formatting
# =========================================================================

def _format_context_length(tokens: int) -> str:
    if tokens >= 1_000_000:
        val = tokens / 1_000_000
        rounded = round(val)
        return f"{rounded}M" if abs(val - rounded) < 0.05 else f"{val:.1f}M"
    elif tokens >= 1_000:
        val = tokens / 1_000
        rounded = round(val)
        return f"{rounded}K" if abs(val - rounded) < 0.05 else f"{val:.1f}K"
    return str(tokens)


# =========================================================================
# Welcome banner
# =========================================================================

def build_welcome_banner(
    console: Console,
    model: str,
    cwd: str,
    tools: List[dict] = None,
    session_id: str = None,
    tool_count: int = 0,
):
    """Build and print a welcome banner with hero on left and info on right."""
    tools = tools or []

    layout_table = Table.grid(padding=(0, 2))
    layout_table.add_column("left", justify="center")
    layout_table.add_column("right", justify="left")

    accent = _skin_color("banner_accent", "#FFBF00")
    dim = _skin_color("banner_dim", "#B8860B")
    text = _skin_color("banner_text", "#FFF8DC")
    session_color = _skin_color("session_border", "#8B8682")

    # Use skin's custom hero art if provided
    try:
        from mlaude.skin_engine import get_active_skin
        _bskin = get_active_skin()
        _hero = _bskin.banner_hero if _bskin.banner_hero else MLAUDE_HERO
    except Exception:
        _bskin = None
        _hero = MLAUDE_HERO

    # Left column: hero art + model info
    left_lines = ["", _hero, ""]
    model_short = model.split("/")[-1] if "/" in model else model
    if len(model_short) > 28:
        model_short = model_short[:25] + "..."
    left_lines.append(f"[{accent}]{model_short}[/] [{dim}]·[/] [{dim}]{cwd}[/]")
    if session_id:
        left_lines.append(f"[dim {session_color}]Session: {session_id[:12]}…[/]")
    left_content = "\n".join(left_lines)

    # Right column: tools & skills
    right_lines = [f"[bold {accent}]Available Tools[/]"]

    # Group tools by toolset
    from mlaude.tools.registry import registry

    all_tools = registry.get_all()
    toolsets_dict: Dict[str, list] = {}
    for tool_name in sorted(all_tools.keys()):
        entry = all_tools[tool_name]
        ts = entry.toolset or "other"
        toolsets_dict.setdefault(ts, []).append(tool_name)

    for toolset in sorted(toolsets_dict.keys()):
        tool_names = toolsets_dict[toolset]
        colored = [f"[{text}]{n}[/]" for n in sorted(tool_names)]
        tools_str = ", ".join(colored)
        if len(", ".join(sorted(tool_names))) > 45:
            short = sorted(tool_names)[:4] + ["..."]
            tools_str = ", ".join(
                f"[{text}]{n}[/]" if n != "..." else "[dim]...[/]"
                for n in short
            )
        right_lines.append(f"[dim {dim}]{toolset}:[/] {tools_str}")

    # Skills section
    right_lines.append("")
    right_lines.append(f"[bold {accent}]Available Skills[/]")
    skills_by_category = get_available_skills()
    total_skills = sum(len(s) for s in skills_by_category.values())
    if skills_by_category:
        for category in sorted(skills_by_category.keys()):
            skill_names = sorted(skills_by_category[category])
            if len(skill_names) > 8:
                skills_str = ", ".join(skill_names[:8]) + f" +{len(skill_names) - 8} more"
            else:
                skills_str = ", ".join(skill_names)
            right_lines.append(f"[dim {dim}]{category}:[/] [{text}]{skills_str}[/]")
    else:
        right_lines.append(f"[dim {dim}]No skills installed[/]")

    # Summary line
    right_lines.append("")
    tc = tool_count or len(all_tools)
    summary_parts = [f"{tc} tools", f"{total_skills} skills", "/help for commands"]
    right_lines.append(f"[dim {dim}]{' · '.join(summary_parts)}[/]")

    # Update check
    try:
        behind = get_update_result(timeout=0.5)
        if behind and behind > 0:
            commits_word = "commit" if behind == 1 else "commits"
            right_lines.append(
                f"[bold yellow]⚠ {behind} {commits_word} behind[/]"
                f"[dim yellow] — run git pull to update[/]"
            )
    except Exception:
        pass

    right_content = "\n".join(right_lines)
    layout_table.add_row(left_content, right_content)

    agent_name = _skin_branding("agent_name", "mlaude")
    title_color = _skin_color("banner_title", "#FFD700")
    border_color = _skin_color("banner_border", "#CD7F32")
    version_label = f"{agent_name} v{VERSION}"

    outer_panel = Panel(
        layout_table,
        title=f"[bold {title_color}]{version_label}[/]",
        border_style=border_color,
        padding=(0, 2),
    )

    console.print()
    term_width = shutil.get_terminal_size().columns
    if term_width >= 60:
        _logo = _bskin.banner_logo if _bskin and _bskin.banner_logo else MLAUDE_LOGO
        console.print(_logo)
        console.print()
    console.print(outer_panel)
