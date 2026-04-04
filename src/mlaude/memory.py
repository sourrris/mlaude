"""Persistent personal memory — reads/writes ~/.mlaude/MEMORY.md."""

import re

from mlaude.config import MEMORY_PATH

_DEFAULT_MEMORY = """\
# What I Know About You

## Identity

## Communication Style

## Work & Projects

## Preferences

## Intellectual Interests

## Discussion Preferences

## Knowledge Depth

## Important People

## Habits & Schedule

## Notes
"""

VALID_SECTIONS = frozenset({
    "Identity",
    "Communication Style",
    "Work & Projects",
    "Preferences",
    "Intellectual Interests",
    "Discussion Preferences",
    "Knowledge Depth",
    "Important People",
    "Habits & Schedule",
    "Notes",
})


def ensure_memory() -> None:
    """Create the default MEMORY.md if it doesn't exist."""
    if not MEMORY_PATH.exists():
        MEMORY_PATH.write_text(_DEFAULT_MEMORY)


def load_memory() -> str:
    """Return the full contents of MEMORY.md for system prompt injection."""
    ensure_memory()
    return MEMORY_PATH.read_text().strip()


def update_memory(section: str, fact: str) -> str:
    """Append a fact under the given ## section heading. Returns status message."""
    if section not in VALID_SECTIONS:
        return f"Invalid section: {section}. Valid: {', '.join(sorted(VALID_SECTIONS))}"

    ensure_memory()
    content = MEMORY_PATH.read_text()

    heading = f"## {section}"
    if heading not in content:
        content += f"\n{heading}\n"

    # Find the section and append the fact after any existing content
    pattern = rf"(## {re.escape(section)}\n)(.*?)(\n## |\Z)"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        section_content = match.group(2).rstrip()
        fact_line = f"- {fact}"

        # Avoid duplicate facts (case-insensitive, whitespace-normalized)
        existing_lines = [l.strip().lower() for l in section_content.splitlines()]
        if fact_line.strip().lower() in existing_lines:
            return f"Already remembered: {fact}"

        new_section = f"{match.group(1)}{section_content}\n{fact_line}\n"
        content = content[: match.start()] + new_section + match.group(3) + content[match.end():]
    else:
        content += f"\n{heading}\n- {fact}\n"

    MEMORY_PATH.write_text(content)
    return f"Remembered in {section}: {fact}"


def delete_memory_fact(section: str, fact: str) -> str:
    """Remove a specific fact from a section. Returns status message."""
    if section not in VALID_SECTIONS:
        return f"Invalid section: {section}. Valid: {', '.join(sorted(VALID_SECTIONS))}"

    ensure_memory()
    content = MEMORY_PATH.read_text()

    heading = f"## {section}"
    if heading not in content:
        return f"Section not found: {section}"

    fact_line = f"- {fact}"
    fact_lower = fact_line.strip().lower()

    lines = content.splitlines(keepends=True)
    new_lines = []
    removed = False
    for line in lines:
        if line.strip().lower() == fact_lower:
            removed = True
            continue
        new_lines.append(line)

    if not removed:
        return f"Fact not found in {section}: {fact}"

    MEMORY_PATH.write_text("".join(new_lines))
    return f"Removed from {section}: {fact}"


def overwrite_memory(raw: str) -> None:
    """Replace the entire MEMORY.md with raw content (for manual edits from UI)."""
    MEMORY_PATH.write_text(raw)
