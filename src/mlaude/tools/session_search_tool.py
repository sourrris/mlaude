"""Session search tool - recall prior discussions across sessions."""

from __future__ import annotations

from mlaude.state import SessionDB
from mlaude.tools.registry import registry, tool_error, tool_result


def _session_search(query: str, limit: int = 5, task_id: str = None) -> str:
    if not query.strip():
        return tool_error("Query is required.")

    db = SessionDB()
    sessions = db.search_sessions(query, limit=max(1, min(limit, 20)))
    if not sessions:
        return tool_result({"query": query, "summary": "No matching sessions found.", "results": []})

    results: list[dict] = []
    for s in sessions:
        msgs = db.get_messages(s["id"], limit=8)
        snippets = [m.get("content", "").strip() for m in msgs if m.get("content")]
        merged = " ".join(snippets)[:500]
        results.append({
            "session_id": s["id"],
            "title": s.get("title", "") or "(untitled)",
            "updated_at": s.get("updated_at", ""),
            "snippet": merged,
        })

    summary = " | ".join(
        f"{r['title']}: {r['snippet'][:120]}" for r in results[:3]
    )

    return tool_result({
        "query": query,
        "summary": summary,
        "results": results,
    })


registry.register(
    name="session_search",
    toolset="memory",
    schema={
        "name": "session_search",
        "description": "Search and summarize prior local sessions for recall.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to recall from prior sessions."},
                "limit": {"type": "integer", "description": "Max sessions to inspect.", "default": 5},
            },
            "required": ["query"],
        },
    },
    handler=lambda args, **kw: _session_search(
        query=args.get("query", ""),
        limit=args.get("limit", 5),
        task_id=kw.get("task_id"),
    ),
)
