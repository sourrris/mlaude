"""WhatsApp adapter — WhatsApp Business Cloud API.

Uses the Meta Graph API for sending messages and a webhook endpoint
for receiving incoming messages.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from mlaude.gateway.base import IncomingMessage, OutgoingMessage, PlatformAdapter

logger = logging.getLogger(__name__)


class WhatsAppAdapter(PlatformAdapter):
    """WhatsApp Business Cloud API adapter."""

    GRAPH_API = "https://graph.facebook.com/v19.0"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.platform_name = "whatsapp"
        self._access_token = config.get("access_token", "")
        self._phone_number_id = config.get("phone_number_id", "")
        self._verify_token = config.get("verify_token", "mlaude_webhook_verify")
        self._allowed_numbers = set(config.get("allowed_numbers", []))

    async def start(self) -> None:
        if not self._access_token:
            raise ValueError("WhatsApp access_token is required")
        if not self._phone_number_id:
            raise ValueError("WhatsApp phone_number_id is required")
        logger.info("WhatsApp adapter ready (webhook mode)")

    async def stop(self) -> None:
        pass  # Webhook-based — nothing to stop

    async def send_message(self, message: OutgoingMessage) -> None:
        url = f"{self.GRAPH_API}/{self._phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": message.chat_id,
            "type": "text",
            "text": {"body": message.text[:4096]},
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
        except Exception as e:
            logger.error("WhatsApp send failed: %s", e)

    # -- Webhook handling --

    def verify_webhook(self, mode: str, token: str, challenge: str) -> str | None:
        """Handle WhatsApp webhook verification (GET request)."""
        if mode == "subscribe" and token == self._verify_token:
            return challenge
        return None

    async def process_webhook(self, body: dict) -> None:
        """Process an incoming WhatsApp webhook payload."""
        try:
            for entry in body.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    messages = value.get("messages", [])

                    for msg in messages:
                        if msg.get("type") != "text":
                            continue

                        sender = msg.get("from", "")

                        # Access control
                        if self._allowed_numbers and sender not in self._allowed_numbers:
                            logger.warning("Blocked message from %s", sender)
                            continue

                        contact = {}
                        contacts = value.get("contacts", [])
                        if contacts:
                            contact = contacts[0]

                        incoming = IncomingMessage(
                            platform="whatsapp",
                            chat_id=sender,
                            user_id=sender,
                            username=contact.get("profile", {}).get("name", ""),
                            text=msg.get("text", {}).get("body", ""),
                            raw=msg,
                        )

                        await self.handle_incoming(incoming)

        except Exception:
            logger.exception("Error processing WhatsApp webhook")
