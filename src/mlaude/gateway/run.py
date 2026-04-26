"""Gateway orchestrator — loads platforms, routes messages, manages lifecycle.

Usage::

    orchestrator = GatewayOrchestrator(config)
    await orchestrator.start()
    # ... serves until shutdown
    await orchestrator.stop()
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from mlaude.gateway.base import IncomingMessage, OutgoingMessage, PlatformAdapter
from mlaude.gateway.session import GatewaySessionManager
from mlaude.state import SessionDB

logger = logging.getLogger(__name__)


class GatewayOrchestrator:
    """Central gateway orchestrator.

    Loads configured platform adapters, wires message routing, and
    manages the agent session lifecycle.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self._adapters: dict[str, PlatformAdapter] = {}
        self._db = SessionDB()
        self._session_mgr = GatewaySessionManager(
            db=self._db, config=self.config
        )
        self._running = False

    def _load_adapters(self) -> None:
        """Load platform adapters based on config."""
        platforms = self.config.get("platforms", {})

        if platforms.get("telegram", {}).get("enabled"):
            try:
                from mlaude.gateway.platforms.telegram import TelegramAdapter
                adapter = TelegramAdapter(platforms["telegram"])
                adapter.on_message = self._handle_message
                self._adapters["telegram"] = adapter
                logger.info("Loaded Telegram adapter")
            except Exception as e:
                logger.error("Failed to load Telegram adapter: %s", e)

        if platforms.get("whatsapp", {}).get("enabled"):
            try:
                from mlaude.gateway.platforms.whatsapp import WhatsAppAdapter
                adapter = WhatsAppAdapter(platforms["whatsapp"])
                adapter.on_message = self._handle_message
                self._adapters["whatsapp"] = adapter
                logger.info("Loaded WhatsApp adapter")
            except Exception as e:
                logger.error("Failed to load WhatsApp adapter: %s", e)

        if platforms.get("email", {}).get("enabled"):
            try:
                from mlaude.gateway.platforms.email import EmailAdapter
                adapter = EmailAdapter(platforms["email"])
                adapter.on_message = self._handle_message
                self._adapters["email"] = adapter
                logger.info("Loaded Email adapter")
            except Exception as e:
                logger.error("Failed to load Email adapter: %s", e)

    async def _handle_message(self, message: IncomingMessage) -> None:
        """Route an incoming message to the appropriate agent."""
        logger.info(
            "Incoming [%s] from %s: %s",
            message.platform,
            message.user_id,
            message.text[:80],
        )

        adapter = self._adapters.get(message.platform)
        if not adapter:
            logger.error("No adapter for platform: %s", message.platform)
            return

        # Get or create agent for this chat
        agent = self._session_mgr.get_or_create_agent(
            chat_id=message.chat_id,
            platform=message.platform,
        )

        # Get conversation history
        history = self._session_mgr.get_conversation_history(
            chat_id=message.chat_id,
            platform=message.platform,
        )

        # Run agent (synchronous — offload to thread)
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None,
                lambda: agent.run_conversation(
                    user_message=message.text,
                    conversation_history=history,
                ),
            )

            response_text = result.get("final_response", "")
            if not response_text:
                response_text = "(No response generated)"

            # Persist messages
            self._db.add_message(
                session_id=agent.session_id,
                role="user",
                content=message.text,
            )
            self._db.add_message(
                session_id=agent.session_id,
                role="assistant",
                content=response_text,
            )

            # Send response
            await adapter.send_message(
                OutgoingMessage(
                    chat_id=message.chat_id,
                    text=response_text,
                    reply_to_message_id=message.reply_to_message_id,
                )
            )

        except Exception as e:
            logger.exception("Error handling message from %s", message.chat_id)
            await adapter.send_message(
                OutgoingMessage(
                    chat_id=message.chat_id,
                    text=f"⚠️ Error: {e}",
                )
            )

    async def start(self) -> None:
        """Start all configured adapters."""
        self._load_adapters()

        if not self._adapters:
            logger.warning("No platform adapters configured")
            return

        self._running = True
        for name, adapter in self._adapters.items():
            try:
                await adapter.start()
                logger.info("Started %s adapter", name)
            except Exception as e:
                logger.error("Failed to start %s: %s", name, e)

    async def stop(self) -> None:
        """Stop all adapters."""
        self._running = False
        for name, adapter in self._adapters.items():
            try:
                await adapter.stop()
                logger.info("Stopped %s adapter", name)
            except Exception:
                logger.exception("Error stopping %s", name)
        self._adapters.clear()

    @property
    def active_platforms(self) -> list[str]:
        return list(self._adapters.keys())
