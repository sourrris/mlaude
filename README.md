# Mlaude

Mlaude is a local-first coding agent focused on terminal workflows.

Current milestone scope is:
- classic interactive CLI (`uv run mlaude`)
- shared session persistence and search
- tool-calling with local safety approvals
- TUI launch flags with graceful fallback to classic CLI

## Quick Start

```bash
uv sync --extra dev
uv run mlaude
```

If `uv sync` fails due to cache permissions in restricted environments, run:
```bash
UV_CACHE_DIR=.uv-cache uv sync --extra dev
```

Useful flags:
- `--resume/-r <session_id>`: resume by id/prefix
- `--continue/-c`: continue most recent session
- `--tui`, `--tui-dev`: attempt TUI launch, fallback if unavailable
- `--yolo`: bypass risky-tool approval prompts

## Commands

Core session commands include `/sessions`, `/resume`, `/search`, `/usage`, `/compress`, `/title`, `/retry`, `/undo`.

## Safety Defaults

Safety policy is local and configurable via `~/.mlaude/config.yaml`:
- `safety.approval_mode`: `ask` (default), `allowlist`, `yolo`
- `safety.command_allowlist`: command prefixes auto-allowed in allowlist mode
- `safety.path_roots`: allowed roots for file write/patch tools

## Notes

- Session database is shared under `~/.mlaude/data/sessions.db`.
- Gateway adapters remain in-repo but are out of scope for this CLI+TUI milestone.
