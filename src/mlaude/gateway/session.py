"""Gateway session manager — maps chat_ids to agent sessions.

Each platform chat_id gets a persistent agent session so conversations
maintain state across messages.
"""

from __future__ import annotations

import logging
import threading

from mlaude.agent import MLaudeAgent
from mlaude.state import SessionDB

logger = logging.getLogger(__name__)


class GatewaySessionManager:
    """Maps platform chat_ids → MLaudeAgent instances with session persistence."""

    def __init__(self, db: SessionDB | None = None, config: dict | None = None):
        self._agents: dict[str, MLaudeAgent] = {}
        self._lock = threading.Lock()
        self._db = db or SessionDB()
        self._config = config or {}

    def get_or_create_agent(
        self,
        chat_id: str,
        platform: str,
        model: str = "",
    ) -> MLaudeAgent:
        """Get existing agent for a chat, or create a new one."""
        key = f"{platform}:{chat_id}"

        with self._lock:
            if key in self._agents:
                return self._agents[key]

        # Check for an existing session in the DB
        sessions = self._db.list_sessions(platform=platform)
        existing = None
        for s in sessions:
            meta = s.get("metadata", "{}")
            try:
                import json
                meta_dict = json.loads(meta) if isinstance(meta, str) else meta
                if meta_dict.get("chat_id") == chat_id:
                    existing = s
                    break
            except Exception:
                continue

        if existing and not existing.get("ended_at"):
            session_id = existing["id"]
            logger.info("Resuming session %s for %s", session_id, key)
        else:
            import json
            session_id = self._db.create_session(
                platform=platform,
                model=model or self._config.get("default_model", ""),
                title=f"{platform}:{chat_id}",
            )
            logger.info("Created new session %s for %s", session_id, key)

        # Create agent
        agent = MLaudeAgent(
            base_url=self._config.get("base_url", ""),
            api_key=self._config.get("api_key", ""),
            model=model or self._config.get("default_model", ""),
            platform=platform,
            session_id=session_id,
            quiet_mode=True,
            session_db=self._db,
        )

        # Load existing conversation history
        history = self._db.get_openai_messages(session_id)
        if history:
            agent._messages = history

        with self._lock:
            self._agents[key] = agent

        return agent

    def remove_agent(self, chat_id: str, platform: str) -> None:
        key = f"{platform}:{chat_id}"
        with self._lock:
            self._agents.pop(key, None)

    def get_conversation_history(
        self, chat_id: str, platform: str
    ) -> list[dict]:
        """Get stored conversation history for a chat."""
        key = f"{platform}:{chat_id}"
        agent = self._agents.get(key)
        if agent:
            return self._db.get_openai_messages(agent.session_id)
        return []
