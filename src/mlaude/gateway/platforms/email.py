"""Email adapter — IMAP polling + SMTP sending.

Polls an IMAP mailbox for new messages, processes them through the agent,
and sends responses via SMTP.  Tracks email threads via Message-ID/In-Reply-To.
"""

from __future__ import annotations

import asyncio
import email
import imaplib
import logging
import smtplib
from email.mime.text import MIMEText
from email.utils import parseaddr
from typing import Any

from mlaude.gateway.base import IncomingMessage, OutgoingMessage, PlatformAdapter

logger = logging.getLogger(__name__)


class EmailAdapter(PlatformAdapter):
    """Email platform adapter using IMAP + SMTP."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.platform_name = "email"

        # IMAP config
        self._imap_host = config.get("imap_host", "")
        self._imap_port = int(config.get("imap_port", 993))
        self._imap_user = config.get("email", "")
        self._imap_pass = config.get("password", "")
        self._imap_folder = config.get("folder", "INBOX")

        # SMTP config
        self._smtp_host = config.get("smtp_host", "")
        self._smtp_port = int(config.get("smtp_port", 587))
        self._smtp_user = config.get("email", "")
        self._smtp_pass = config.get("password", "")
        self._from_addr = config.get("from_address", config.get("email", ""))

        # Polling
        self._poll_interval = int(config.get("poll_interval", 30))
        self._allowed_senders = set(config.get("allowed_senders", []))
        self._running = False
        self._poll_task: asyncio.Task | None = None

        # Thread tracking
        self._message_ids: dict[str, str] = {}  # chat_id → last Message-ID

    async def start(self) -> None:
        if not self._imap_host or not self._imap_user:
            raise ValueError("Email IMAP host and email are required")

        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info(
            "Email adapter started — polling %s every %ds",
            self._imap_host, self._poll_interval,
        )

    async def stop(self) -> None:
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

    async def send_message(self, message: OutgoingMessage) -> None:
        """Send an email response via SMTP."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._send_smtp, message)

    def _send_smtp(self, message: OutgoingMessage) -> None:
        try:
            msg = MIMEText(message.text, "plain", "utf-8")
            msg["From"] = self._from_addr
            msg["To"] = message.chat_id
            msg["Subject"] = "Re: mlaude"

            # Thread via In-Reply-To
            last_msg_id = self._message_ids.get(message.chat_id)
            if last_msg_id:
                msg["In-Reply-To"] = last_msg_id
                msg["References"] = last_msg_id

            with smtplib.SMTP(self._smtp_host, self._smtp_port) as smtp:
                smtp.starttls()
                smtp.login(self._smtp_user, self._smtp_pass)
                smtp.send_message(msg)

            logger.info("Email sent to %s", message.chat_id)
        except Exception as e:
            logger.error("SMTP send failed: %s", e)

    # -- IMAP polling --

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self._check_inbox)
            except Exception:
                logger.exception("Error polling IMAP")

            await asyncio.sleep(self._poll_interval)

    def _check_inbox(self) -> None:
        try:
            imap = imaplib.IMAP4_SSL(self._imap_host, self._imap_port)
            imap.login(self._imap_user, self._imap_pass)
            imap.select(self._imap_folder)

            # Search for unread messages
            _, msg_nums = imap.search(None, "UNSEEN")
            if not msg_nums[0]:
                imap.logout()
                return

            for num in msg_nums[0].split():
                _, msg_data = imap.fetch(num, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    continue

                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                sender_name, sender_addr = parseaddr(msg.get("From", ""))

                # Access control
                if self._allowed_senders and sender_addr not in self._allowed_senders:
                    logger.info("Ignoring email from %s", sender_addr)
                    continue

                # Extract body
                body = self._get_text_body(msg)
                if not body.strip():
                    continue

                # Track message ID for threading
                message_id = msg.get("Message-ID", "")
                if message_id:
                    self._message_ids[sender_addr] = message_id

                incoming = IncomingMessage(
                    platform="email",
                    chat_id=sender_addr,
                    user_id=sender_addr,
                    username=sender_name,
                    text=body.strip(),
                    raw={"subject": msg.get("Subject", "")},
                )

                # Dispatch via asyncio from sync context
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(self.handle_incoming(incoming))

                # Mark as read
                imap.store(num, "+FLAGS", "\\Seen")

            imap.logout()

        except Exception:
            logger.exception("IMAP check failed")

    @staticmethod
    def _get_text_body(msg: email.message.Message) -> str:
        """Extract plain text body from an email message."""
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == "text/plain" and not part.get("Content-Disposition"):
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        return payload.decode(charset, errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
        return ""
