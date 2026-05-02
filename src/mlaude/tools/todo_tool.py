"""Todo tool — per-session task planning and tracking.

Provides a simple task list that the agent can use to plan and track
multi-step work within a session.
"""

from __future__ import annotations

import uuid

from mlaude.tools.registry import registry, tool_error, tool_result

# In-memory task store (per-session, keyed by task_id/session_id)
_todos: dict[str, list[dict]] = {}


def _todo(action: str, text: str = "", item_id: str = "",
          status: str = "", task_id: str = None) -> str:
    """Manage per-session todo list."""
    session = task_id or "default"

    if session not in _todos:
        _todos[session] = []

    todos = _todos[session]

    if action == "add":
        if not text:
            return tool_error("Text is required for add.")
        item = {
            "id": uuid.uuid4().hex[:8],
            "text": text,
            "status": "pending",
        }
        todos.append(item)
        return tool_result({"action": "added", "item": item, "total": len(todos)})

    elif action == "list":
        return tool_result({"items": todos, "total": len(todos)})

    elif action == "update":
        if not item_id:
            return tool_error("item_id is required for update.")
        for item in todos:
            if item["id"] == item_id:
                if text:
                    item["text"] = text
                if status:
                    item["status"] = status
                return tool_result({"action": "updated", "item": item})
        return tool_error(f"Item not found: {item_id}")

    elif action == "done":
        if not item_id:
            return tool_error("item_id is required for done.")
        for item in todos:
            if item["id"] == item_id:
                item["status"] = "done"
                return tool_result({"action": "done", "item": item})
        return tool_error(f"Item not found: {item_id}")

    elif action == "remove":
        if not item_id:
            return tool_error("item_id is required for remove.")
        for i, item in enumerate(todos):
            if item["id"] == item_id:
                removed = todos.pop(i)
                return tool_result({"action": "removed", "item": removed})
        return tool_error(f"Item not found: {item_id}")

    elif action == "clear":
        count = len(todos)
        todos.clear()
        return tool_result({"action": "cleared", "removed": count})

    return tool_error(f"Unknown action: {action}")


registry.register(
    name="todo",
    toolset="planning",
    schema={
        "name": "todo",
        "description": (
            "Manage a per-session task list for planning multi-step work. "
            "Use 'add' to add tasks, 'list' to view, 'done' to mark complete, "
            "'update' to modify, 'remove' to delete, 'clear' to reset."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "list", "update", "done", "remove", "clear"],
                    "description": "Action to perform.",
                },
                "text": {
                    "type": "string",
                    "description": "Task description (for add/update).",
                },
                "item_id": {
                    "type": "string",
                    "description": "Task ID (for update/done/remove).",
                },
                "status": {
                    "type": "string",
                    "description": "New status (for update).",
                },
            },
            "required": ["action"],
        },
    },
    handler=lambda args, **kw: _todo(
        action=args.get("action", ""),
        text=args.get("text", ""),
        item_id=args.get("item_id", ""),
        status=args.get("status", ""),
        task_id=kw.get("task_id"),
    ),
)
