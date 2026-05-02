from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from mlaude.settings import (
    SAFETY_APPROVAL_MODE,
    SAFETY_COMMAND_ALLOWLIST,
    SAFETY_PATH_ROOTS,
    load_config,
)

RISKY_TOOLS = {"terminal", "write_file", "patch", "execute_code"}


@dataclass
class SafetyDecision:
    allowed: bool
    requires_approval: bool = False
    reason: str = ""


class SafetyPolicy:
    def __init__(self) -> None:
        self._yolo_override = False

    def set_yolo(self, enabled: bool) -> None:
        self._yolo_override = enabled

    def _config(self) -> dict:
        return load_config() or {}

    def mode(self) -> str:
        if self._yolo_override:
            return "yolo"
        cfg = self._config().get("safety", {})
        return str(cfg.get("approval_mode", SAFETY_APPROVAL_MODE or "ask")).lower()

    def allowlist(self) -> list[str]:
        cfg = self._config().get("safety", {})
        vals = cfg.get("command_allowlist", SAFETY_COMMAND_ALLOWLIST)
        if isinstance(vals, str):
            vals = [vals]
        return [str(v).strip() for v in vals if str(v).strip()]

    def path_roots(self) -> list[str]:
        cfg = self._config().get("safety", {})
        vals = cfg.get("path_roots", SAFETY_PATH_ROOTS)
        if isinstance(vals, str):
            vals = [vals]
        roots = [str(v).strip() for v in vals if str(v).strip()]
        if not roots:
            roots = [os.getcwd()]
        return roots

    def _is_command_allowlisted(self, command: str) -> bool:
        cmd = (command or "").strip()
        if not cmd:
            return False
        return any(cmd.startswith(prefix) for prefix in self.allowlist())

    def _is_path_allowed(self, path: str) -> bool:
        if not path:
            return True
        real = str(Path(path).expanduser().resolve())
        for root in self.path_roots():
            try:
                base = str(Path(root).expanduser().resolve())
            except Exception:
                continue
            if real == base or real.startswith(base + os.sep):
                return True
        return False

    def evaluate(self, tool_name: str, args: dict, approval_granted: bool = False) -> SafetyDecision:
        if tool_name not in RISKY_TOOLS:
            return SafetyDecision(allowed=True)

        mode = self.mode()
        if mode == "yolo":
            return SafetyDecision(allowed=True)

        if tool_name == "terminal":
            if self._is_command_allowlisted(str(args.get("command", ""))):
                return SafetyDecision(allowed=True)

        if tool_name in {"write_file", "patch"}:
            if not self._is_path_allowed(str(args.get("path", ""))):
                return SafetyDecision(
                    allowed=False,
                    reason="path_outside_roots",
                )

        if mode == "allowlist":
            return SafetyDecision(
                allowed=False,
                reason="blocked_by_allowlist",
            )

        if mode == "ask" and not approval_granted:
            return SafetyDecision(
                allowed=False,
                requires_approval=True,
                reason="approval_required",
            )

        return SafetyDecision(allowed=True)


policy = SafetyPolicy()
