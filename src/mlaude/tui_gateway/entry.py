from __future__ import annotations

import logging
import os

from mlaude.settings import DEFAULT_CHAT_MODEL, DEFAULT_TEMPERATURE, LLM_BASE_URL
from mlaude.state import SessionDB
from mlaude.tui_gateway.server import GatewayServer, GatewayState
from mlaude.tui_gateway.transport import JsonRpcTransport


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    state = GatewayState(
        db=SessionDB(),
        model=os.environ.get("MLAUDE_DEFAULT_CHAT_MODEL", DEFAULT_CHAT_MODEL),
        base_url=os.environ.get("MLAUDE_LLM_BASE_URL", LLM_BASE_URL),
        temperature=float(os.environ.get("MLAUDE_DEFAULT_TEMPERATURE", str(DEFAULT_TEMPERATURE))),
        provider=os.environ.get("MLAUDE_TUI_PROVIDER") or os.environ.get("MLAUDE_PROVIDER") or None,
        resume_id=os.environ.get("MLAUDE_TUI_RESUME") or None,
        quiet=os.environ.get("MLAUDE_QUIET", "").strip().lower() in {"1", "true", "yes", "on"},
    )
    server = GatewayServer(JsonRpcTransport(), state=state)
    server.serve()


if __name__ == "__main__":
    main()
