"""Memory tool — lets the model save facts about the user."""

from mlaude.memory import VALID_SECTIONS, update_memory
from mlaude.tools_base import Tool, ToolResult


class UpdateMemoryTool(Tool):
    name = "update_memory"
    description = (
        "Save a fact about the user for future reference. "
        "Use when the user shares personal info, preferences, habits, "
        "or explicitly says 'remember that...'. "
        "Do NOT save trivial or temporary information."
    )
    parameters = {
        "type": "object",
        "properties": {
            "section": {
                "type": "string",
                "enum": sorted(VALID_SECTIONS),
                "description": "Which memory section to store the fact under",
            },
            "fact": {
                "type": "string",
                "description": "The fact to remember (concise, one sentence)",
            },
        },
        "required": ["section", "fact"],
    }

    async def run(self, *, section: str, fact: str) -> ToolResult:
        result = update_memory(section, fact)
        return ToolResult(output=result)
