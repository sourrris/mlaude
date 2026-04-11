#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
E2E_HOME="$ROOT_DIR/.tmp/e2e-home"

rm -rf "$E2E_HOME"
mkdir -p "$E2E_HOME"

cd "$ROOT_DIR"
MLAUDE_ENABLE_TEST_RUNTIME=1 \
MLAUDE_HOME="$E2E_HOME" \
.venv/bin/python -m uvicorn mlaude.server:app --host 127.0.0.1 --port 7475
