"""Memory tools — save and delete facts about the user."""

from mlaude.memory import VALID_SECTIONS, delete_memory_fact, update_memory
from mlaude.tools_base import Tool, ToolResult


class UpdateMemoryTool(Tool):
    name = "update_memory"
    description = (
        "Save a fact about the user for future reference. "
        "Use when the user shares personal info, preferences, habits, projects, "
        "or explicitly says 'remember that...'. "
        "Use 'Intellectual Interests' for topics, questions, or concepts they care about. "
        "Use 'Discussion Preferences' for how they like to engage on ideas. "
        "Use 'Knowledge Depth' for areas where they have deep expertise (avoids over-explaining). "
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


class DeleteMemoryFactTool(Tool):
    name = "delete_memory_fact"
    description = (
        "Remove an outdated or incorrect fact from memory. "
        "Use when the user says something is no longer true, asks to forget something, "
        "or when a stored fact contradicts what they've just told you."
    )
    parameters = {
        "type": "object",
        "properties": {
            "section": {
                "type": "string",
                "enum": sorted(VALID_SECTIONS),
                "description": "The section the fact is stored in",
            },
            "fact": {
                "type": "string",
                "description": "The exact fact to remove (must match what was stored)",
            },
        },
        "required": ["section", "fact"],
    }

    async def run(self, *, section: str, fact: str) -> ToolResult:
        result = delete_memory_fact(section, fact)
        return ToolResult(output=result)
