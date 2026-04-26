"""Terminal tool — shell command execution with timeout and output management.

Registered via the tool registry for auto-discovery.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
from pathlib import Path

from mlaude.settings import TERMINAL_TIMEOUT_SECONDS
from mlaude.tools.registry import registry, tool_error, tool_result

# ---------------------------------------------------------------------------
# Persistent working directory tracker
# ---------------------------------------------------------------------------

_cwd_lock = threading.Lock()
_cwd: str | None = None


def get_cwd() -> str:
    """Return the terminal's tracked working directory."""
    global _cwd
    with _cwd_lock:
        if _cwd is None:
            _cwd = os.getcwd()
        return _cwd


def set_cwd(path: str) -> None:
    """Update the tracked working directory."""
    global _cwd
    with _cwd_lock:
        _cwd = path


# ---------------------------------------------------------------------------
# terminal tool
# ---------------------------------------------------------------------------


def _terminal(
    command: str,
    timeout: int | None = None,
    working_dir: str | None = None,
    task_id: str | None = None,
) -> str:
    """Execute a shell command and return its output."""
    if not command.strip():
        return tool_error("Empty command.")

    effective_timeout = timeout or TERMINAL_TIMEOUT_SECONDS
    cwd = working_dir or get_cwd()

    # Validate working directory
    if not Path(cwd).is_dir():
        return tool_error(f"Working directory not found: {cwd}")

    # Handle cd commands — update tracked cwd
    stripped = command.strip()
    if stripped.startswith("cd ") or stripped == "cd":
        return _handle_cd(stripped, cwd)

    env = os.environ.copy()
    env["PAGER"] = "cat"  # Avoid interactive pagers

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=effective_timeout,
            cwd=cwd,
            env=env,
            # Kill the entire process group on timeout
            preexec_fn=os.setsid if os.name != "nt" else None,
        )

        stdout = result.stdout
        stderr = result.stderr

        # Truncate large output
        max_output = 32_000
        stdout_truncated = False
        stderr_truncated = False

        if len(stdout) > max_output:
            stdout = stdout[:max_output]
            stdout_truncated = True
        if len(stderr) > max_output:
            stderr = stderr[:max_output]
            stderr_truncated = True

        output: dict = {
            "exit_code": result.returncode,
            "cwd": cwd,
        }

        if stdout:
            output["stdout"] = stdout
        if stderr:
            output["stderr"] = stderr
        if stdout_truncated:
            output["stdout_truncated"] = True
        if stderr_truncated:
            output["stderr_truncated"] = True

        return tool_result(output)

    except subprocess.TimeoutExpired:
        return tool_error(
            f"Command timed out after {effective_timeout}s",
            command=command,
        )
    except Exception as e:
        return tool_error(f"Command execution failed: {e}")


def _handle_cd(command: str, current_cwd: str) -> str:
    """Handle cd commands by updating the tracked working directory."""
    parts = command.split(maxsplit=1)
    if len(parts) == 1:
        # Bare "cd" → go home
        target = str(Path.home())
    else:
        target = parts[1].strip()
        # Handle ~ expansion
        target = os.path.expanduser(target)
        # Handle relative paths
        if not os.path.isabs(target):
            target = os.path.join(current_cwd, target)

    target = os.path.realpath(target)

    if not os.path.isdir(target):
        return tool_error(f"Directory not found: {target}")

    set_cwd(target)
    return tool_result({"cwd": target})


registry.register(
    name="terminal",
    toolset="terminal",
    schema={
        "name": "terminal",
        "description": (
            "Execute a shell command in the terminal. Returns stdout, stderr, "
            "and exit code. Use this for running programs, installing packages, "
            "git operations, file system commands, etc. "
            "The working directory persists between calls."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                },
                "timeout": {
                    "type": "integer",
                    "description": f"Timeout in seconds. Default {TERMINAL_TIMEOUT_SECONDS}.",
                },
                "working_dir": {
                    "type": "string",
                    "description": "Override working directory for this command. Optional.",
                },
            },
            "required": ["command"],
        },
    },
    handler=lambda args, **kw: _terminal(
        command=args.get("command", ""),
        timeout=args.get("timeout"),
        working_dir=args.get("working_dir"),
        task_id=kw.get("task_id"),
    ),
)
