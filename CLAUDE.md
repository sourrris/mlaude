# CLAUDE.md

## Project

Mlaude is a local-first research workspace built on:

- `src/mlaude`: FastAPI + SQLAlchemy backend
- `frontend`: Next.js App Router frontend
- `Ollama`: the only chat and embedding runtime

The current harness is intentionally bounded. Each user turn creates a persisted
`agent_run` with fixed step types:

- `classify`
- `retrieve_local`
- `plan_search`
- `search_web`
- `fetch_page`
- `extract_page`
- `rerank_evidence`
- `synthesize`
- `verify_citations`

The product goal is evidence discipline and inspectable runs, not open-ended
agent autonomy.

## Commands

```bash
# Backend deps
python -m pip install -e ".[dev]"

# Frontend deps
cd frontend && npm install

# Start backend
uv run mlaude --host 127.0.0.1 --port 7474

# Start frontend
cd frontend && npm run dev

# Backend sanity / tests
python -m compileall src
pytest

# Frontend production build
cd frontend && npm run build
```

## Runtime Requirements

- Ollama must be running locally.
- `MLAUDE_DEFAULT_EMBEDDING_MODEL` defaults to `nomic-embed-text`.
- Chat and embeddings both stay local; no cloud providers are used in this milestone.

## Architecture Notes

- Chat remains on `/api/chat/stream`, but the server now emits run packets alongside
  message packets.
- Session detail includes both chat history and persisted runs.
- Local retrieval is hybrid: lexical scoring + Ollama embeddings.
- Web research uses DDGS for search plus structured fetch/extract, with
  `trafilatura` first and `readability-lxml` / HTML fallback behind it.
- The frontend exposes a session-level `Chat | Runs` toggle. `Runs` is the
  inspection surface for plan, steps, evidence, and stop reasons.

## Important Files

- `src/mlaude/server.py`: orchestration, API routes, run persistence, stream packets
- `src/mlaude/retrieval.py`: local chunk index, embeddings, hybrid scoring, reranking
- `src/mlaude/tools/web_search.py`: DDGS adapter, URL normalization, fetch/extract
- `src/mlaude/models.py`: sessions, messages, files, `agent_runs`, `agent_steps`
- `frontend/components/chat/chat-workspace.tsx`: session shell and `Chat | Runs` mode
- `frontend/components/chat/runs-panel.tsx`: run inspection UI
- `evals/scenarios/research-harness.json`: checked-in harness scenarios

## Conventions

- Prefer grounded answers with citations over speculative completeness.
- If citations cannot be verified against the evidence pool, stop with insufficient evidence.
- Do not add cloud runtimes or SaaS search APIs in this milestone.
- Keep Ollama as the only runtime surface for both generation and embeddings.
