"""Platform adapter base class.

Every messaging platform (Telegram, WhatsApp, Email) implements this
interface to normalize messages into a common format the agent can consume.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class IncomingMessage:
    """Normalized incoming message from any platform."""

    platform: str
    chat_id: str
    user_id: str
    text: str
    username: str = ""
    attachments: list[dict] = field(default_factory=list)
    reply_to_message_id: str | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class OutgoingMessage:
    """Normalized outgoing response to any platform."""

    chat_id: str
    text: str
    parse_mode: str = "markdown"
    reply_to_message_id: str | None = None
    attachments: list[dict] = field(default_factory=list)


class PlatformAdapter(ABC):
    """Abstract adapter for a messaging platform.

    Subclasses implement:
    - ``start()`` — begin polling or register webhooks
    - ``stop()`` — clean shutdown
    - ``send_message()`` — send a response back to the user
    - ``on_message`` — callback set by the gateway orchestrator
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.platform_name: str = ""
        self._on_message = None

    @property
    def on_message(self):
        return self._on_message

    @on_message.setter
    def on_message(self, callback):
        """Set by the gateway orchestrator to handle incoming messages."""
        self._on_message = callback

    @abstractmethod
    async def start(self) -> None:
        """Start the adapter (polling, webhook registration, etc.)."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Clean shutdown."""
        ...

    @abstractmethod
    async def send_message(self, message: OutgoingMessage) -> None:
        """Send a response to the platform."""
        ...

    async def handle_incoming(self, message: IncomingMessage) -> None:
        """Process an incoming message through the registered callback."""
        if self._on_message:
            await self._on_message(message)
        else:
            logger.warning(
                "No message handler registered for %s", self.platform_name
            )
