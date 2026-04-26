"""File operation tools — read, write, patch, search.

Registered via the tool registry for auto-discovery.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from mlaude.tools.registry import registry, tool_error, tool_result

# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------


def _read_file(path: str, start_line: int = None, end_line: int = None,
               task_id: str = None) -> str:
    """Read file contents, optionally a line range."""
    p = Path(path).expanduser()
    if not p.exists():
        return tool_error(f"File not found: {path}")
    if not p.is_file():
        return tool_error(f"Not a file: {path}")

    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return tool_error(f"Failed to read {path}: {e}")

    lines = text.splitlines(keepends=True)
    total = len(lines)

    if start_line is not None or end_line is not None:
        s = max(1, start_line or 1) - 1  # 1-indexed → 0-indexed
        e = min(total, end_line or total)
        lines = lines[s:e]
        # Add line numbers
        numbered = "".join(
            f"{s + i + 1}: {line}" for i, line in enumerate(lines)
        )
        return tool_result({
            "path": str(p),
            "total_lines": total,
            "showing": f"lines {s+1}-{e}",
            "content": numbered,
        })

    # Truncate very large files
    from mlaude.settings import MAX_FILE_READ_CHARS
    content = text
    truncated = False
    if len(content) > MAX_FILE_READ_CHARS:
        content = content[:MAX_FILE_READ_CHARS]
        truncated = True

    return tool_result({
        "path": str(p),
        "total_lines": total,
        "truncated": truncated,
        "content": content,
    })


registry.register(
    name="read_file",
    toolset="file",
    schema={
        "name": "read_file",
        "description": (
            "Read the contents of a file. Supports optional line ranges. "
            "Returns the file content with line numbers when using ranges."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file.",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Start line (1-indexed, inclusive). Optional.",
                },
                "end_line": {
                    "type": "integer",
                    "description": "End line (1-indexed, inclusive). Optional.",
                },
            },
            "required": ["path"],
        },
    },
    handler=lambda args, **kw: _read_file(
        path=args.get("path", ""),
        start_line=args.get("start_line"),
        end_line=args.get("end_line"),
        task_id=kw.get("task_id"),
    ),
)


# ---------------------------------------------------------------------------
# write_file
# ---------------------------------------------------------------------------


def _write_file(path: str, content: str, overwrite: bool = False,
                task_id: str = None) -> str:
    """Write content to a file.  Creates parent directories."""
    p = Path(path).expanduser()

    if p.exists() and not overwrite:
        return tool_error(
            f"File already exists: {path}. Set overwrite=true to replace."
        )

    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    except Exception as e:
        return tool_error(f"Failed to write {path}: {e}")

    return tool_result({
        "path": str(p),
        "bytes_written": len(content.encode("utf-8")),
        "created": not p.exists(),
    })


registry.register(
    name="write_file",
    toolset="file",
    schema={
        "name": "write_file",
        "description": (
            "Write content to a file. Creates parent directories if needed. "
            "Set overwrite=true to replace an existing file."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative path for the file.",
                },
                "content": {
                    "type": "string",
                    "description": "The full content to write.",
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "If true, overwrite existing file. Default false.",
                    "default": False,
                },
            },
            "required": ["path", "content"],
        },
    },
    handler=lambda args, **kw: _write_file(
        path=args.get("path", ""),
        content=args.get("content", ""),
        overwrite=args.get("overwrite", False),
        task_id=kw.get("task_id"),
    ),
)


# ---------------------------------------------------------------------------
# patch
# ---------------------------------------------------------------------------


def _patch(path: str, target: str, replacement: str,
           task_id: str = None) -> str:
    """Replace exact text in a file.  Fuzzy-matches with whitespace normalization."""
    p = Path(path).expanduser()
    if not p.exists():
        return tool_error(f"File not found: {path}")

    try:
        original = p.read_text(encoding="utf-8")
    except Exception as e:
        return tool_error(f"Failed to read {path}: {e}")

    # Exact match first
    if target in original:
        updated = original.replace(target, replacement, 1)
        p.write_text(updated, encoding="utf-8")
        return tool_result({
            "path": str(p),
            "match": "exact",
            "replacements": 1,
        })

    # Fuzzy match: normalize whitespace
    def normalize(s: str) -> str:
        return re.sub(r'\s+', ' ', s.strip())

    norm_target = normalize(target)
    lines = original.splitlines(keepends=True)

    # Try sliding window
    target_lines = target.splitlines()
    window = len(target_lines)

    for i in range(len(lines) - window + 1):
        chunk = "".join(lines[i:i + window])
        if normalize(chunk) == norm_target:
            updated = "".join(lines[:i]) + replacement + "".join(lines[i + window:])
            p.write_text(updated, encoding="utf-8")
            return tool_result({
                "path": str(p),
                "match": "fuzzy",
                "replacements": 1,
                "matched_at_line": i + 1,
            })

    return tool_error(
        f"Target text not found in {path}. "
        "Ensure the target exactly matches the file content."
    )


registry.register(
    name="patch",
    toolset="file",
    schema={
        "name": "patch",
        "description": (
            "Replace a specific block of text in a file. Provide the exact "
            "text to find (target) and its replacement. Uses fuzzy whitespace "
            "matching if exact match fails."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to patch.",
                },
                "target": {
                    "type": "string",
                    "description": "The exact text to find and replace.",
                },
                "replacement": {
                    "type": "string",
                    "description": "The new text to insert.",
                },
            },
            "required": ["path", "target", "replacement"],
        },
    },
    handler=lambda args, **kw: _patch(
        path=args.get("path", ""),
        target=args.get("target", ""),
        replacement=args.get("replacement", ""),
        task_id=kw.get("task_id"),
    ),
)


# ---------------------------------------------------------------------------
# search_files
# ---------------------------------------------------------------------------


def _search_files(
    query: str,
    path: str = ".",
    pattern: str = None,
    case_sensitive: bool = True,
    max_results: int = 50,
    task_id: str = None,
) -> str:
    """Search for text in files using ripgrep (with grep fallback)."""
    search_path = Path(path).expanduser()
    if not search_path.exists():
        return tool_error(f"Path not found: {path}")

    # Try ripgrep first, fall back to grep
    cmd: list[str] = []
    use_rg = _has_command("rg")

    if use_rg:
        cmd = ["rg", "--json", "-m", str(max_results)]
        if not case_sensitive:
            cmd.append("-i")
        if pattern:
            cmd.extend(["-g", pattern])
        cmd.extend([query, str(search_path)])
    else:
        cmd = ["grep", "-rn", f"--max-count={max_results}"]
        if not case_sensitive:
            cmd.append("-i")
        if pattern:
            cmd.extend(["--include", pattern])
        cmd.extend([query, str(search_path)])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(search_path) if search_path.is_dir() else None,
        )
    except FileNotFoundError:
        return tool_error("Neither ripgrep (rg) nor grep found.")
    except subprocess.TimeoutExpired:
        return tool_error("Search timed out after 30 seconds.")

    matches: list[dict] = []

    if use_rg:
        for line in result.stdout.splitlines():
            try:
                entry = json.loads(line)
                if entry.get("type") == "match":
                    data = entry["data"]
                    matches.append({
                        "file": data["path"]["text"],
                        "line": data["line_number"],
                        "content": data["lines"]["text"].rstrip(),
                    })
            except (json.JSONDecodeError, KeyError):
                continue
    else:
        for line in result.stdout.splitlines()[:max_results]:
            parts = line.split(":", 2)
            if len(parts) >= 3:
                matches.append({
                    "file": parts[0],
                    "line": int(parts[1]) if parts[1].isdigit() else 0,
                    "content": parts[2].rstrip(),
                })

    return tool_result({
        "query": query,
        "path": str(search_path),
        "total_matches": len(matches),
        "matches": matches[:max_results],
    })


def _has_command(name: str) -> bool:
    """Check if a command exists on PATH."""
    try:
        subprocess.run(
            ["which", name],
            capture_output=True,
            timeout=5,
        )
        return True
    except Exception:
        return False


registry.register(
    name="search_files",
    toolset="file",
    schema={
        "name": "search_files",
        "description": (
            "Search for text content within files. Uses ripgrep for fast "
            "pattern matching with grep as fallback. Returns matching lines "
            "with file paths and line numbers."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search text or regex pattern.",
                },
                "path": {
                    "type": "string",
                    "description": "Directory or file to search in. Default: current directory.",
                    "default": ".",
                },
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to filter files (e.g. '*.py'). Optional.",
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "Case-sensitive search. Default true.",
                    "default": True,
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results. Default 50.",
                    "default": 50,
                },
            },
            "required": ["query"],
        },
    },
    handler=lambda args, **kw: _search_files(
        query=args.get("query", ""),
        path=args.get("path", "."),
        pattern=args.get("pattern"),
        case_sensitive=args.get("case_sensitive", True),
        max_results=args.get("max_results", 50),
        task_id=kw.get("task_id"),
    ),
)
