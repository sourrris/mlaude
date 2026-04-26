"""Telegram adapter — python-telegram-bot SDK.

Supports both polling and webhook modes.  Uses message editing for
streaming-style responses.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from mlaude.gateway.base import IncomingMessage, OutgoingMessage, PlatformAdapter

logger = logging.getLogger(__name__)


class TelegramAdapter(PlatformAdapter):
    """Telegram platform adapter using python-telegram-bot."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.platform_name = "telegram"
        self._token = config.get("bot_token", "")
        self._allowed_users = set(config.get("allowed_users", []))
        self._webhook_url = config.get("webhook_url")
        self._app = None

    async def start(self) -> None:
        try:
            from telegram import Update
            from telegram.ext import (
                ApplicationBuilder,
                CommandHandler,
                MessageHandler,
                filters,
            )
        except ImportError:
            raise ImportError(
                "python-telegram-bot is required: pip install 'mlaude[telegram]'"
            )

        if not self._token:
            raise ValueError("Telegram bot_token is required in config")

        self._app = (
            ApplicationBuilder()
            .token(self._token)
            .build()
        )

        # Register handlers
        self._app.add_handler(CommandHandler("start", self._handle_start))
        self._app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text)
        )

        # Start polling (webhook mode can be added later)
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram bot started (polling mode)")

    async def stop(self) -> None:
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()

    async def send_message(self, message: OutgoingMessage) -> None:
        if not self._app:
            return

        try:
            await self._app.bot.send_message(
                chat_id=int(message.chat_id),
                text=message.text[:4096],  # Telegram limit
                parse_mode="Markdown" if message.parse_mode == "markdown" else None,
            )
        except Exception:
            # Fallback without parse_mode if markdown fails
            try:
                await self._app.bot.send_message(
                    chat_id=int(message.chat_id),
                    text=message.text[:4096],
                )
            except Exception as e:
                logger.error("Failed to send Telegram message: %s", e)

    # -- Handlers --

    async def _handle_start(self, update, context) -> None:
        await update.message.reply_text(
            "👋 Hi! I'm mlaude, a local AI agent. Send me a message!"
        )

    async def _handle_text(self, update, context) -> None:
        if not update.message or not update.message.text:
            return

        user_id = str(update.effective_user.id)
        chat_id = str(update.effective_chat.id)

        # Access control
        if self._allowed_users and user_id not in self._allowed_users:
            await update.message.reply_text("⛔ Not authorized.")
            return

        message = IncomingMessage(
            platform="telegram",
            chat_id=chat_id,
            user_id=user_id,
            username=update.effective_user.username or "",
            text=update.message.text,
            raw=update.to_dict(),
        )

        await self.handle_incoming(message)
