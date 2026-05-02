# Repository Guidelines

## Project Structure & Module Organization
Core code lives in `src/mlaude/`, organized by responsibility: `providers/` for model backends, `tools/` for callable tools, `gateway/` for platform adapters and webhooks, and `cli.py` as the main entrypoint.  
Tests are in `tests/` (`test_*.py`), with focused suites for agent loop, provider registry, and tools.  
Utility scripts are in `scripts/` (for example, `scripts/qa_agent.py`).  
Project configuration is in `pyproject.toml`; runtime logs may appear in repo root during local QA.

## Build, Test, and Development Commands
- `uv sync --extra dev`: install project and developer dependencies.
- `uv run mlaude`: start the interactive CLI agent locally.
- `uv run pytest`: run all tests in `tests/`.
- `uv run pytest tests/test_tools.py`: run a focused test module.
- `uv run ruff check src tests`: lint code for style and quality issues.
- `python -m compileall src`: quick compile check before a PR.

Use Python 3.11+ (`requires-python = ">=3.11"`).

## Coding Style & Naming Conventions
Follow existing Python style: 4-space indentation, type hints on public interfaces, and small cohesive modules.  
Ruff is configured with `line-length = 100`; keep imports and wrapping consistent with that limit.  
Naming: modules/functions in `snake_case`, classes in `PascalCase`, constants in `UPPER_SNAKE_CASE`.  
Prefer explicit provider/tool names (`openai_provider.py`, `terminal_tool.py`) over generic filenames.

## Testing Guidelines
Test framework is `pytest` (with `pytest-asyncio` available; `asyncio_mode = "auto"`).  
Name tests `test_<behavior>.py` and test functions `test_<expected_outcome>()`.  
Mock external LLM/tool/network boundaries (see `tests/test_agent.py`) so tests stay deterministic and offline-friendly.  
For behavioral changes, add or update targeted tests in the nearest module-level test file.

## Commit & Pull Request Guidelines
Recent history favors Conventional Commit prefixes: `feat:`, `fix:`, `refactor:` (for example, `refactor: ... gateway support`).  
Keep commit scopes focused and describe user-visible behavior changes, not just file edits.  
PRs should include:
- concise summary and motivation,
- linked issue (if applicable),
- test/lint commands run and results,
- sample CLI output or screenshots only when behavior/UI output changed.
