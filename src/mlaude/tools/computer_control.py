"""Desktop-control seam reserved for future non-browser automation."""

from __future__ import annotations

from typing import Protocol


class ComputerController(Protocol):
    """Future interface for screenshot, mouse, keyboard, and app control."""

    def is_available(self) -> bool:
        ...


class NoopComputerController:
    """Stub implementation for this browser-only phase."""

    def is_available(self) -> bool:
        return False
