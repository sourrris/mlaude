"""Tests for file and terminal tools (μ3)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mlaude.tools.registry import registry
from mlaude.model_tools import discover_tools


class TestFileTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        discover_tools()

    def setUp(self):
        self.reg = registry
        self.tmpdir = tempfile.mkdtemp()

    def test_read_file(self):
        # Create a test file
        test_file = Path(self.tmpdir) / "test.txt"
        test_file.write_text("line 1\nline 2\nline 3\n")

        result = self.reg.dispatch("read_file", {"path": str(test_file)})
        data = json.loads(result)
        assert data["total_lines"] == 3
        assert "line 1" in data["content"]

    def test_read_file_with_range(self):
        test_file = Path(self.tmpdir) / "ranged.txt"
        test_file.write_text("a\nb\nc\nd\ne\n")

        result = self.reg.dispatch("read_file", {
            "path": str(test_file),
            "start_line": 2,
            "end_line": 4,
        })
        data = json.loads(result)
        assert "2: b" in data["content"]
        assert "4: d" in data["content"]

    def test_read_file_not_found(self):
        result = self.reg.dispatch("read_file", {"path": "/nonexistent/file.txt"})
        data = json.loads(result)
        assert "error" in data

    def test_write_file(self):
        test_file = Path(self.tmpdir) / "output.txt"
        result = self.reg.dispatch("write_file", {
            "path": str(test_file),
            "content": "hello world",
        })
        data = json.loads(result)
        assert "error" not in data
        assert test_file.read_text() == "hello world"

    def test_write_file_no_overwrite(self):
        test_file = Path(self.tmpdir) / "existing.txt"
        test_file.write_text("original")

        result = self.reg.dispatch("write_file", {
            "path": str(test_file),
            "content": "new content",
        })
        data = json.loads(result)
        assert "error" in data
        assert test_file.read_text() == "original"

    def test_write_file_with_overwrite(self):
        test_file = Path(self.tmpdir) / "overwrite.txt"
        test_file.write_text("original")

        result = self.reg.dispatch("write_file", {
            "path": str(test_file),
            "content": "replaced",
            "overwrite": True,
        })
        data = json.loads(result)
        assert "error" not in data
        assert test_file.read_text() == "replaced"

    def test_patch_exact(self):
        test_file = Path(self.tmpdir) / "patch.txt"
        test_file.write_text("hello world\nfoo bar\n")

        result = self.reg.dispatch("patch", {
            "path": str(test_file),
            "target": "foo bar",
            "replacement": "baz qux",
        })
        data = json.loads(result)
        assert data["match"] == "exact"
        assert "baz qux" in test_file.read_text()

    def test_patch_not_found(self):
        test_file = Path(self.tmpdir) / "nopatch.txt"
        test_file.write_text("hello world\n")

        result = self.reg.dispatch("patch", {
            "path": str(test_file),
            "target": "nonexistent text",
            "replacement": "new text",
        })
        data = json.loads(result)
        assert "error" in data


class TestTerminalTool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        discover_tools()

    def setUp(self):
        self.reg = registry

    def test_simple_command(self):
        result = self.reg.dispatch("terminal", {"command": "echo hello"})
        data = json.loads(result)
        assert data["exit_code"] == 0
        assert "hello" in data["stdout"]

    def test_command_failure(self):
        result = self.reg.dispatch("terminal", {"command": "false"})
        data = json.loads(result)
        assert data["exit_code"] != 0

    def test_empty_command(self):
        result = self.reg.dispatch("terminal", {"command": ""})
        data = json.loads(result)
        assert "error" in data

    def test_timeout(self):
        result = self.reg.dispatch("terminal", {
            "command": "sleep 10",
            "timeout": 1,
        })
        data = json.loads(result)
        assert "error" in data
        assert "timed out" in data["error"].lower()


if __name__ == "__main__":
    unittest.main()
