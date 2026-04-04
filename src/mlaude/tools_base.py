"""Tool system foundation — base class, registry, events."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolResult:
    output: str
    error: bool = False


@dataclass(frozen=True)
class ToolEvent:
    phase: str  # "start" | "done"
    tool_name: str
    tool_input: dict
    tool_output: str | None = None


class Tool(ABC):
    name: str
    description: str
    parameters: dict  # JSON Schema for the function parameters

    @abstractmethod
    async def run(self, **kwargs) -> ToolResult: ...

    def schema(self) -> dict:
        """Return Ollama-format tool schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def schemas(self) -> list[dict]:
        return [t.schema() for t in self._tools.values()]

    async def call(self, name: str, args: dict) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(output=f"Unknown tool: {name}", error=True)
        try:
            return await tool.run(**args)
        except Exception as e:
            return ToolResult(output=f"Tool error: {e}", error=True)
