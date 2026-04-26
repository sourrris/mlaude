"""Tests for session state (μ5), gateway (μ7), commands (μ9), and self-improving tools (μ10)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mlaude.state import SessionDB
from mlaude.commands import resolve_command, COMMANDS, COMMANDS_BY_CATEGORY


class TestSessionDB(unittest.TestCase):
    """Test SQLite session store."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db = SessionDB(self.tmp.name)

    def tearDown(self):
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_create_session(self):
        sid = self.db.create_session(platform="cli", model="test-model")
        assert sid is not None
        session = self.db.get_session(sid)
        assert session is not None
        assert session["platform"] == "cli"
        assert session["model"] == "test-model"

    def test_list_sessions(self):
        self.db.create_session(platform="cli")
        self.db.create_session(platform="telegram")
        sessions = self.db.list_sessions()
        assert len(sessions) == 2

        # Filter by platform
        cli_sessions = self.db.list_sessions(platform="cli")
        assert len(cli_sessions) == 1

    def test_add_and_get_messages(self):
        sid = self.db.create_session()
        self.db.add_message(sid, "user", "Hello!")
        self.db.add_message(sid, "assistant", "Hi there!")

        messages = self.db.get_messages(sid)
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["content"] == "Hi there!"

    def test_get_openai_messages(self):
        sid = self.db.create_session()
        self.db.add_message(sid, "user", "Hello")
        self.db.add_message(sid, "assistant", "Hi")

        openai_msgs = self.db.get_openai_messages(sid)
        assert len(openai_msgs) == 2
        assert openai_msgs[0] == {"role": "user", "content": "Hello"}
        assert openai_msgs[1] == {"role": "assistant", "content": "Hi"}

    def test_end_session(self):
        sid = self.db.create_session()
        self.db.end_session(sid)
        session = self.db.get_session(sid)
        assert session["ended_at"] is not None

    def test_delete_session(self):
        sid = self.db.create_session()
        assert self.db.delete_session(sid) is True
        assert self.db.get_session(sid) is None
        assert self.db.delete_session("nonexistent") is False

    def test_update_title_and_tokens(self):
        sid = self.db.create_session()
        self.db.update_session_title(sid, "Test Session")
        self.db.update_session_tokens(sid, 100, 0.01)

        session = self.db.get_session(sid)
        assert session["title"] == "Test Session"
        assert session["total_tokens"] == 100

    def test_search(self):
        sid = self.db.create_session()
        self.db.add_message(sid, "user", "Tell me about quantum computing")

        results = self.db.search_sessions("quantum")
        assert len(results) >= 1

    def test_stats(self):
        self.db.create_session()
        stats = self.db.get_stats()
        assert stats["sessions"] == 1
        assert stats["messages"] == 0


class TestCommands(unittest.TestCase):
    """Test slash command registry."""

    def test_resolve_basic(self):
        canonical, args = resolve_command("/help")
        assert canonical == "help"
        assert args == ""

    def test_resolve_with_args(self):
        canonical, args = resolve_command("/model gpt-4o")
        assert canonical == "model"
        assert args == "gpt-4o"

    def test_resolve_alias(self):
        canonical, args = resolve_command("/q")
        assert canonical == "quit"

    def test_resolve_alias_clear(self):
        canonical, args = resolve_command("/clear")
        assert canonical == "new"

    def test_resolve_unknown(self):
        canonical, args = resolve_command("/nonexistent")
        assert canonical == ""
        assert args == "/nonexistent"

    def test_not_a_command(self):
        canonical, args = resolve_command("hello world")
        assert canonical == ""
        assert args == "hello world"

    def test_commands_by_category(self):
        assert "Session" in COMMANDS_BY_CATEGORY
        assert "Info" in COMMANDS_BY_CATEGORY
        assert "Exit" in COMMANDS_BY_CATEGORY

    def test_all_commands_have_names(self):
        for name, cmd in COMMANDS.items():
            assert cmd.name, f"Command {name} has no canonical name"
            assert cmd.category, f"Command {name} has no category"


class TestSelfImprovingTools(unittest.TestCase):
    """Test μ10 tools: skills, memory, todo, code_execution."""

    @classmethod
    def setUpClass(cls):
        from mlaude.model_tools import discover_tools
        discover_tools()

    def test_todo_lifecycle(self):
        from mlaude.tools.registry import registry
        # Add
        result = json.loads(registry.dispatch("todo", {"action": "add", "text": "Test task"}))
        assert result.get("item", {}).get("text") == "Test task"
        item_id = result["item"]["id"]

        # List
        result = json.loads(registry.dispatch("todo", {"action": "list"}))
        assert result["total"] >= 1

        # Done
        result = json.loads(registry.dispatch("todo", {"action": "done", "item_id": item_id}))
        assert result["item"]["status"] == "done"

        # Remove
        result = json.loads(registry.dispatch("todo", {"action": "remove", "item_id": item_id}))
        assert result.get("action") == "removed"

    def test_memory_lifecycle(self):
        from mlaude.tools.registry import registry
        # Store
        result = json.loads(registry.dispatch("memory", {
            "action": "store", "key": "test_key", "value": "test_value"
        }))
        assert result.get("action") == "stored"

        # Recall
        result = json.loads(registry.dispatch("memory", {
            "action": "recall", "key": "test_key"
        }))
        assert result.get("value") == "test_value"

        # Search
        result = json.loads(registry.dispatch("memory", {
            "action": "search", "key": "test"
        }))
        assert len(result.get("results", [])) >= 1

        # Forget
        result = json.loads(registry.dispatch("memory", {
            "action": "forget", "key": "test_key"
        }))
        assert result.get("deleted") is True

    def test_skills_lifecycle(self):
        from mlaude.tools.registry import registry
        # Create
        result = json.loads(registry.dispatch("skill_manage", {
            "action": "create",
            "name": "_test_skill",
            "content": "# Test Skill\n\nThis is a test.",
        }))
        assert "error" not in result

        # List
        result = json.loads(registry.dispatch("skills_list", {}))
        names = [s["name"] for s in result.get("skills", [])]
        assert "_test_skill" in names

        # View
        result = json.loads(registry.dispatch("skill_view", {"name": "_test_skill"}))
        assert "Test Skill" in result.get("content", "")

        # Delete
        result = json.loads(registry.dispatch("skill_manage", {
            "action": "delete", "name": "_test_skill"
        }))
        assert result.get("deleted") is True

    def test_code_execution(self):
        from mlaude.tools.registry import registry
        result = json.loads(registry.dispatch("execute_code", {
            "code": "print('hello world')"
        }))
        assert result.get("exit_code") == 0
        assert "hello world" in result.get("stdout", "")

    def test_code_execution_error(self):
        from mlaude.tools.registry import registry
        result = json.loads(registry.dispatch("execute_code", {
            "code": "raise ValueError('test error')"
        }))
        assert result.get("exit_code") != 0
        assert "test error" in result.get("stderr", "")

    def test_delegate_tool_registered(self):
        from mlaude.tools.registry import registry
        assert registry.get("delegate_task") is not None


class TestGatewayBase(unittest.TestCase):
    """Test gateway infrastructure."""

    def test_incoming_message(self):
        from mlaude.gateway.base import IncomingMessage
        msg = IncomingMessage(
            platform="telegram",
            chat_id="123",
            user_id="456",
            text="Hello!",
        )
        assert msg.platform == "telegram"
        assert msg.text == "Hello!"

    def test_outgoing_message(self):
        from mlaude.gateway.base import OutgoingMessage
        msg = OutgoingMessage(chat_id="123", text="Hi!")
        assert msg.parse_mode == "markdown"

    def test_orchestrator_init(self):
        from mlaude.gateway.run import GatewayOrchestrator
        orchestrator = GatewayOrchestrator({})
        assert orchestrator.active_platforms == []


if __name__ == "__main__":
    unittest.main()
