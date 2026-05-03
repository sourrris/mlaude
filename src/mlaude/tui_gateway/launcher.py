from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from mlaude.settings import PROJECT_ROOT

UI_TUI_DIR = PROJECT_ROOT / "ui-tui"


class TuiLaunchError(RuntimeError):
    """Raised when the Node/Ink TUI cannot be bootstrapped or launched."""


def can_launch_tui() -> tuple[bool, str]:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return False, "TTY not detected"
    if shutil.which("node") is None:
        return False, "node not found"
    if shutil.which("npm") is None:
        return False, "npm not found"
    return True, "ok"


def resolve_tui_dir() -> Path:
    custom_dir = os.environ.get("MLAUDE_TUI_DIR", "").strip()
    return (Path(custom_dir).expanduser() if custom_dir else UI_TUI_DIR).resolve()


def _dist_entry(tui_dir: Path) -> Path:
    return tui_dir / "dist" / "index.js"


def _package_lock(tui_dir: Path) -> Path:
    return tui_dir / "package-lock.json"


def build_launcher_env(
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
) -> dict[str, str]:
    env = os.environ.copy()
    env["MLAUDE_TUI"] = "dev" if tui_dev else "1"
    env["MLAUDE_TUI_DIR"] = str(resolve_tui_dir())
    env["MLAUDE_TUI_RESUME"] = resume_id or ""
    env["MLAUDE_TUI_PROVIDER"] = provider or ""
    env["MLAUDE_PYTHON_SRC_ROOT"] = str(PROJECT_ROOT / "src")
    env["MLAUDE_PYTHON"] = sys.executable
    env["MLAUDE_CWD"] = cwd
    env["MLAUDE_LLM_BASE_URL"] = base_url
    env["MLAUDE_DEFAULT_CHAT_MODEL"] = model
    env["MLAUDE_DEFAULT_TEMPERATURE"] = str(temperature)
    if provider:
        env["MLAUDE_PROVIDER"] = provider
    if skin:
        env["MLAUDE_SKIN"] = skin
    if yolo:
        env["MLAUDE_SAFETY_APPROVAL_MODE"] = "yolo"
    return env


def _run_step(args: list[str], cwd: Path, env: dict[str, str], step: str) -> None:
    proc = subprocess.run(
        args,
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode == 0:
        return
    detail = (proc.stderr or proc.stdout or "").strip()
    message = f"{step} failed with exit code {proc.returncode}"
    if detail:
        message += f": {detail}"
    raise TuiLaunchError(message)


def _needs_build(tui_dir: Path) -> bool:
    dist_entry = _dist_entry(tui_dir)
    if not dist_entry.exists():
        return True
    dist_mtime = dist_entry.stat().st_mtime
    for path in tui_dir.rglob("*"):
        if not path.is_file():
            continue
        if path == dist_entry or "node_modules" in path.parts or "dist" in path.parts:
            continue
        if path.stat().st_mtime > dist_mtime:
            return True
    return False


def _ensure_bootstrap(tui_dir: Path, env: dict[str, str]) -> None:
    package_json = tui_dir / "package.json"
    if not package_json.exists():
        raise TuiLaunchError(f"TUI package not found at {package_json}")
    if (tui_dir / "node_modules").exists():
        return
    install_cmd = ["npm", "ci"] if _package_lock(tui_dir).exists() else ["npm", "install"]
    _run_step(install_cmd, tui_dir, env, "TUI dependency bootstrap")


def _ensure_build(tui_dir: Path, env: dict[str, str], tui_dev: bool) -> None:
    if tui_dev:
        return
    if not _needs_build(tui_dir):
        return
    _run_step(["npm", "run", "build"], cwd=tui_dir, env=env, step="TUI build")


def launch_tui(
    *,
    cwd: str,
    resume_id: str | None,
    provider: str | None,
    model: str,
    base_url: str,
    temperature: float,
    yolo: bool,
    skin: str | None,
    tui_dev: bool = False,
) -> int:
    ok, reason = can_launch_tui()
    if not ok:
        raise TuiLaunchError(reason)

    tui_dir = resolve_tui_dir()
    env = build_launcher_env(
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

    _ensure_bootstrap(tui_dir, env)
    _ensure_build(tui_dir, env, tui_dev)

    command = ["npm", "run", "dev"] if tui_dev else ["node", str(_dist_entry(tui_dir))]
    proc = subprocess.run(command, cwd=str(tui_dir), env=env, check=False)
    return proc.returncode
