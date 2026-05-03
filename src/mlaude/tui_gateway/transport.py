from __future__ import annotations

import json
import sys
import threading
from collections.abc import Callable
from typing import Any


JsonDict = dict[str, Any]


class JsonRpcTransport:
    """Line-delimited stdio JSON-RPC transport."""

    def __init__(self, *, stdin=None, stdout=None):
        self._stdin = stdin or sys.stdin
        self._stdout = stdout or sys.stdout
        self._write_lock = threading.Lock()

    def send(self, payload: JsonDict) -> None:
        data = json.dumps(payload, ensure_ascii=True)
        with self._write_lock:
            self._stdout.write(data + "\n")
            self._stdout.flush()

    def send_event(self, method: str, params: JsonDict | None = None) -> None:
        self.send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def send_result(self, request_id: str | int | None, result: Any) -> None:
        self.send({"jsonrpc": "2.0", "id": request_id, "result": result})

    def send_error(
        self,
        request_id: str | int | None,
        code: int,
        message: str,
        data: JsonDict | None = None,
    ) -> None:
        payload: JsonDict = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }
        if data:
            payload["error"]["data"] = data
        self.send(payload)

    def serve(self, handler: Callable[[JsonDict], None]) -> None:
        while True:
            line = self._stdin.readline()
            if line == "":
                break
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                self.send_event("gateway.stderr", {"message": f"Invalid JSON: {exc}"})
                continue
            handler(message)
