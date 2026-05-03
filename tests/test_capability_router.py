from __future__ import annotations

from mlaude.capability_router import ROUTES, classify_capability_route, filter_tools_for_route
from mlaude.tools.registry import ToolRegistry


def test_route_precedence_prefers_browser_over_fresh_web() -> None:
    route = classify_capability_route("open the latest docs page and click login")
    assert route.name == "browser_task"


def test_route_classifies_fresh_web_and_delegation() -> None:
    assert classify_capability_route("what is the latest release").name == "fresh_web"
    assert classify_capability_route("compare these options").name == "delegation_candidate"


def test_filter_tools_for_route_limits_to_route_specific_tools() -> None:
    platform_tools = ["read_file", "web_search", "browser_navigate", "delegate_task"]
    filtered = filter_tools_for_route(ROUTES["fresh_web"], platform_tools)
    assert filtered == ["web_search"]


def test_registry_definitions_can_filter_by_tool_name() -> None:
    registry = ToolRegistry()
    registry.register(
        name="tool_a",
        toolset="alpha",
        schema={"name": "tool_a", "description": "", "parameters": {}},
        handler=lambda args, **kw: "{}",
    )
    registry.register(
        name="tool_b",
        toolset="beta",
        schema={"name": "tool_b", "description": "", "parameters": {}},
        handler=lambda args, **kw: "{}",
    )

    definitions = registry.get_definitions(allowed_tool_names=["tool_b"])
    assert [item["function"]["name"] for item in definitions] == ["tool_b"]
