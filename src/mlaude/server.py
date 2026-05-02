"""Gateway webhook server — FastAPI endpoints for WhatsApp and Email.

Telegram uses its own polling/webhook via python-telegram-bot.
This server handles WhatsApp webhook verification and incoming messages,
plus any future webhook-based platforms.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

logger = logging.getLogger(__name__)

# Global reference to the orchestrator (set at startup)
_orchestrator = None


def set_orchestrator(orchestrator) -> None:
    global _orchestrator
    _orchestrator = orchestrator


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start/stop the gateway orchestrator with the server."""
    if _orchestrator:
        await _orchestrator.start()
    yield
    if _orchestrator:
        await _orchestrator.stop()


app = FastAPI(title="mlaude-gateway", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    platforms = _orchestrator.active_platforms if _orchestrator else []
    return {"status": "ok", "platforms": platforms}


# ---------------------------------------------------------------------------
# WhatsApp webhooks
# ---------------------------------------------------------------------------


@app.get("/webhook/whatsapp")
async def whatsapp_verify(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """WhatsApp webhook verification (GET)."""
    if not _orchestrator:
        return PlainTextResponse("Not configured", status_code=503)

    adapter = _orchestrator._adapters.get("whatsapp")
    if adapter and hasattr(adapter, "verify_webhook"):
        result = adapter.verify_webhook(hub_mode or "", hub_token or "", hub_challenge or "")
        if result:
            return PlainTextResponse(result)

    return PlainTextResponse("Verification failed", status_code=403)


@app.post("/webhook/whatsapp")
async def whatsapp_incoming(request: Request):
    """WhatsApp incoming message webhook (POST)."""
    if not _orchestrator:
        return {"status": "not configured"}

    body = await request.json()
    adapter = _orchestrator._adapters.get("whatsapp")
    if adapter and hasattr(adapter, "process_webhook"):
        await adapter.process_webhook(body)

    return {"status": "ok"}
