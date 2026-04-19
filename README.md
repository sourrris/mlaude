# Mlaude

Mlaude is a local AI workspace for chat, file-based retrieval, and visible tool execution.

It runs as:

- a FastAPI backend in `src/mlaude`
- a Next.js frontend in `frontend`
- an Ollama-backed local model runtime

The current product is focused on a single-user local workflow:

- start a chat immediately
- upload local files
- ask grounded questions over those files
- watch the response stream in with intermediate steps
- open citations and supporting sources in a side panel
- configure the local model runtime from Settings

## Current Features

- chat-first workspace shell with sidebar, recents, files, and settings
- streaming assistant responses
- visible tool/retrieval timeline cards
- file upload for chat-scoped files and shared library files
- local retrieval with citations
- source sidebar for cited and related documents
- Ollama model discovery and default model selection
- built-in tools for internal search, file reading, Python execution, and URL reading
- Playwright end-to-end coverage for the main workspace flow

## Stack

- Frontend: Next.js App Router, React, TypeScript, Tailwind
- Backend: FastAPI, SQLAlchemy
- Model runtime: Ollama
- Storage: SQLAlchemy-backed local app database
- Retrieval: local chunked file index with citation mapping

## Repository Layout

- `src/mlaude`: backend app, runtime, retrieval, file ingestion, API routes
- `frontend/app`: Next.js routes
- `frontend/components`: workspace UI, chat UI, files UI, settings UI
- `frontend/lib`: API client, stream packet state handling, shared types
- `frontend/tests`: Playwright E2E tests
- `scripts`: local helper scripts

## Requirements

- Python 3.11+
- Node.js 20+
- npm
- Ollama installed locally

## Setup

### 1. Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Frontend dependencies

```bash
cd frontend
npm install
cd ..
```

### 3. Start Ollama

If Ollama is not already running:

```bash
ollama serve
```

If you want to preload a model:

```bash
ollama pull <model_name>
```

The app will automatically discover and let you choose from any models you have installed.

## Running The App

Start the backend:

```bash
source .venv/bin/activate
uv run mlaude --host 127.0.0.1 --port 7474
```

Start the frontend in another terminal:

```bash
cd frontend
npm run dev
```

Open:

- `http://127.0.0.1:3000`

## Runtime Notes

- App data is stored under `.local/mlaude/` by default.
- The backend listens on port `7474` by default.
- The frontend talks to `http://127.0.0.1:7474` by default.
- Ollama base URL, model selection, and temperature are managed in the Settings page.
- `MLAUDE_DATABASE_URL` can be set to point SQLAlchemy at a different database.
- `MLAUDE_HOME` can be set to move local app data somewhere else.

## Development Helpers

Run the frontend production build:

```bash
cd frontend
npm run build
```

Run E2E tests:

```bash
cd frontend
npm run test:e2e
```

Run the backend compile check:

```bash
.venv/bin/python -m compileall src
```

## Test Runtime

For deterministic local testing without a live Ollama dependency:

```bash
MLAUDE_ENABLE_TEST_RUNTIME=1 uv run mlaude --host 127.0.0.1 --port 7474
```

The E2E suite uses this mode automatically for backend test startup.
