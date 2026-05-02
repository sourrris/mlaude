from __future__ import annotations

import shutil
import sys


def can_launch_tui() -> tuple[bool, str]:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return False, "TTY not detected"
    if shutil.which("node") is None:
        return False, "Node.js not found"
    return True, "ok"
