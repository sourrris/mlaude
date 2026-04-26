"""Skills tool — markdown skill files for persistent knowledge.

Skills are markdown files stored in ``~/.mlaude/skills/`` that the agent
can create, read, and use to improve its capabilities over time.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from mlaude.settings import SKILLS_DIR
from mlaude.tools.registry import registry, tool_error, tool_result


def _skills_list(task_id: str = None) -> str:
    """List all available skills."""
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    skills = []
    for f in sorted(SKILLS_DIR.glob("**/*.md")):
        rel = f.relative_to(SKILLS_DIR)
        content = f.read_text(encoding="utf-8", errors="replace")
        # Extract title from first heading
        title = ""
        for line in content.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        skills.append({
            "name": str(rel).replace(".md", ""),
            "path": str(f),
            "title": title or str(rel.stem),
            "size": len(content),
        })
    return tool_result({"skills": skills, "total": len(skills), "dir": str(SKILLS_DIR)})


def _skill_view(name: str, task_id: str = None) -> str:
    """View the content of a skill."""
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    # Try exact match, then with .md extension
    candidates = [
        SKILLS_DIR / name,
        SKILLS_DIR / f"{name}.md",
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            content = p.read_text(encoding="utf-8", errors="replace")
            return tool_result({"name": name, "content": content, "path": str(p)})

    return tool_error(f"Skill not found: {name}")


def _skill_manage(action: str, name: str, content: str = "",
                  task_id: str = None) -> str:
    """Create, update, or delete a skill."""
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    path = SKILLS_DIR / f"{name}.md"

    if action == "create" or action == "update":
        if not content:
            return tool_error("Content is required for create/update")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return tool_result({
            "action": action,
            "name": name,
            "path": str(path),
            "size": len(content),
        })

    elif action == "delete":
        if path.exists():
            path.unlink()
            return tool_result({"action": "delete", "name": name, "deleted": True})
        return tool_error(f"Skill not found: {name}")

    return tool_error(f"Unknown action: {action}. Use create, update, or delete.")


# Register tools
for _name, _desc, _handler, _params in [
    (
        "skills_list",
        "List all available skills (markdown knowledge files).",
        lambda args, **kw: _skills_list(task_id=kw.get("task_id")),
        {"type": "object", "properties": {}, "required": []},
    ),
    (
        "skill_view",
        "View the content of a specific skill by name.",
        lambda args, **kw: _skill_view(
            name=args.get("name", ""), task_id=kw.get("task_id")
        ),
        {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Skill name (without .md extension)."},
            },
            "required": ["name"],
        },
    ),
    (
        "skill_manage",
        "Create, update, or delete a skill. Skills are persistent markdown knowledge files.",
        lambda args, **kw: _skill_manage(
            action=args.get("action", ""),
            name=args.get("name", ""),
            content=args.get("content", ""),
            task_id=kw.get("task_id"),
        ),
        {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["create", "update", "delete"],
                           "description": "Action to perform."},
                "name": {"type": "string", "description": "Skill name."},
                "content": {"type": "string", "description": "Markdown content (for create/update)."},
            },
            "required": ["action", "name"],
        },
    ),
]:
    registry.register(
        name=_name, toolset="skills",
        schema={"name": _name, "description": _desc, "parameters": _params},
        handler=_handler,
    )
