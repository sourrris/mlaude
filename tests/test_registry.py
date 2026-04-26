"""Tests for the tool registry and model_tools orchestration (μ2)."""

from __future__ import annotations

import json
import os
import unittest

from mlaude.tools.registry import ToolRegistry, tool_error, tool_result


class TestToolResult(unittest.TestCase):
    def test_tool_result_dict(self):
        r = tool_result({"key": "value"})
        assert json.loads(r) == {"key": "value"}

    def test_tool_result_string(self):
        r = tool_result("hello")
        assert r == "hello"

    def test_tool_error(self):
        r = tool_error("something broke", code=42)
        data = json.loads(r)
        assert data["error"] == "something broke"
        assert data["code"] == 42


class TestToolRegistry(unittest.TestCase):
    def setUp(self):
        self.reg = ToolRegistry()

    def test_register_and_get(self):
        self.reg.register(
            name="test_tool",
            toolset="test",
            schema={"name": "test_tool", "description": "A test", "parameters": {}},
            handler=lambda args, **kw: json.dumps({"ok": True}),
        )
        entry = self.reg.get("test_tool")
        assert entry is not None
        assert entry.name == "test_tool"
        assert entry.toolset == "test"

    def test_deregister(self):
        self.reg.register(
            name="temp",
            toolset="test",
            schema={"name": "temp", "description": "temp", "parameters": {}},
            handler=lambda args, **kw: "{}",
        )
        assert self.reg.deregister("temp") is True
        assert self.reg.get("temp") is None
        assert self.reg.deregister("nonexistent") is False

    def test_get_definitions(self):
        self.reg.register(
            name="tool_a",
            toolset="alpha",
            schema={"name": "tool_a", "description": "A", "parameters": {}},
            handler=lambda args, **kw: "{}",
        )
        self.reg.register(
            name="tool_b",
            toolset="beta",
            schema={"name": "tool_b", "description": "B", "parameters": {}},
            handler=lambda args, **kw: "{}",
        )

        # All tools
        defs = self.reg.get_definitions()
        assert len(defs) == 2

        # Filter by enabled toolset
        defs = self.reg.get_definitions(enabled_toolsets=["alpha"])
        assert len(defs) == 1
        assert defs[0]["function"]["name"] == "tool_a"

        # Filter by disabled toolset
        defs = self.reg.get_definitions(disabled_toolsets=["alpha"])
        assert len(defs) == 1
        assert defs[0]["function"]["name"] == "tool_b"

    def test_dispatch(self):
        self.reg.register(
            name="echo",
            toolset="test",
            schema={"name": "echo", "description": "Echo", "parameters": {}},
            handler=lambda args, **kw: json.dumps({"echo": args.get("msg", "")}),
        )
        result = self.reg.dispatch("echo", {"msg": "hello"})
        assert json.loads(result) == {"echo": "hello"}

    def test_dispatch_unknown_tool(self):
        result = self.reg.dispatch("nonexistent", {})
        data = json.loads(result)
        assert "error" in data
        assert "Unknown tool" in data["error"]

    def test_availability_check(self):
        self.reg.register(
            name="needs_key",
            toolset="test",
            schema={"name": "needs_key", "description": "x", "parameters": {}},
            handler=lambda args, **kw: "{}",
            requires_env=["VERY_UNLIKELY_ENV_VAR_12345"],
        )
        entry = self.reg.get("needs_key")
        assert entry is not None
        assert entry.is_available() is False

        # Should be excluded from definitions
        defs = self.reg.get_definitions()
        names = [d["function"]["name"] for d in defs]
        assert "needs_key" not in names

    def test_list_toolsets(self):
        self.reg.register(
            name="t1", toolset="alpha",
            schema={"name": "t1", "description": "", "parameters": {}},
            handler=lambda args, **kw: "{}",
        )
        self.reg.register(
            name="t2", toolset="beta",
            schema={"name": "t2", "description": "", "parameters": {}},
            handler=lambda args, **kw: "{}",
        )
        assert self.reg.list_toolsets() == ["alpha", "beta"]

    def test_reset(self):
        self.reg.register(
            name="x", toolset="test",
            schema={"name": "x", "description": "", "parameters": {}},
            handler=lambda args, **kw: "{}",
        )
        self.reg.reset()
        assert len(self.reg.get_all()) == 0


class TestToolDiscovery(unittest.TestCase):
    """Test that built-in tools are discovered."""

    def test_builtin_tools_discovered(self):
        from mlaude.model_tools import discover_tools
        from mlaude.tools.registry import registry as singleton_reg

        discover_tools()
        all_tools = singleton_reg.get_all()
        assert len(all_tools) >= 5  # read_file, write_file, patch, search_files, terminal
        assert singleton_reg.get("read_file") is not None
        assert singleton_reg.get("terminal") is not None
        assert singleton_reg.get("write_file") is not None


if __name__ == "__main__":
    unittest.main()
