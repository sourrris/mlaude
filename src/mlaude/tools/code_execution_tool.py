"""Code execution tool — safe Python code execution in a sandbox.

Runs Python code in a subprocess with timeout and output capture.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from mlaude.settings import PYTHON_TOOL_TIMEOUT_SECONDS
from mlaude.tools.registry import registry, tool_error, tool_result


def _execute_code(
    code: str,
    language: str = "python",
    timeout: int | None = None,
    task_id: str = None,
) -> str:
    """Execute code in a subprocess."""
    effective_timeout = timeout or PYTHON_TOOL_TIMEOUT_SECONDS

    if language != "python":
        return tool_error(f"Unsupported language: {language}. Only Python is supported.")

    if not code.strip():
        return tool_error("Empty code.")

    # Write code to a temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=effective_timeout,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )

        stdout = result.stdout
        stderr = result.stderr

        # Truncate
        max_out = 16_000
        if len(stdout) > max_out:
            stdout = stdout[:max_out] + "\n... (truncated)"
        if len(stderr) > max_out:
            stderr = stderr[:max_out] + "\n... (truncated)"

        output: dict = {"exit_code": result.returncode}
        if stdout:
            output["stdout"] = stdout
        if stderr:
            output["stderr"] = stderr

        return tool_result(output)

    except subprocess.TimeoutExpired:
        return tool_error(f"Code execution timed out after {effective_timeout}s")
    except Exception as e:
        return tool_error(f"Code execution failed: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


registry.register(
    name="execute_code",
    toolset="terminal",  # Group with terminal tools
    schema={
        "name": "execute_code",
        "description": (
            "Execute Python code in a sandboxed subprocess. Returns stdout, "
            "stderr, and exit code. Use this for calculations, data processing, "
            "or any programmatic task."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute.",
                },
                "timeout": {
                    "type": "integer",
                    "description": f"Timeout in seconds (default {PYTHON_TOOL_TIMEOUT_SECONDS}).",
                },
            },
            "required": ["code"],
        },
    },
    handler=lambda args, **kw: _execute_code(
        code=args.get("code", ""),
        language=args.get("language", "python"),
        timeout=args.get("timeout"),
        task_id=kw.get("task_id"),
    ),
)
