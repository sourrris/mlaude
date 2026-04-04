---
  # CLAUDE.md                                                                                                                                                  
                                                                                                                                                               
  This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.                                                       
                                                                                                                                                               
  ## Project                                             
            
  Mlaude is a local-first personal AI agent — a lightweight web UI that connects to Ollama for LLM inference. Single-process Python backend (FastAPI +
  WebSocket), single-file frontend (vanilla JS), SQLite persistence. No Node.js, no build step, no tests.                                                      
                                                                                                         
  ## Commands                                                                                                                                                  
                                                         
  ```bash
  uv sync                    # install Python dependencies
  cd frontend && npm install # install frontend dependencies (first time)
  cd frontend && npm run build  # build React app → static/
  uv run mlaude              # start server on http://0.0.0.0:7474
  uv run mlaude --port 8080  # custom port

  # Frontend dev mode (hot reload, proxies to FastAPI on :7474):
  cd frontend && npm run dev # runs on http://localhost:5173                        
                                                                                                                                                               
  Requires Ollama running locally with llama3.1:8b-instruct-q4_K_M pulled.
                                                                                                                                                               
  Architecture                                           
                                                                                                                                                               
  Browser (WebSocket) → FastAPI server → Ollama (async streaming)
                           ↕
                      SQLite (aiosqlite)

  - WebSocket /ws is the main chat protocol. Client sends JSON messages (message, new_session, list_sessions, load_session, delete_session), server responds   
  with streaming token chunks, done, error, sessions, history, etc.
  - SOUL.md (repo root) is the system prompt identity, loaded at each request with current datetime appended.                                                  
  - ~/.mlaude/sessions.db stores all sessions and messages. Created automatically on first run.                                                                
   
  Source Layout                                                                                                                                                
                                                         
  All backend code is in src/mlaude/:                                                                                                                          
  - config.py — paths (~/.mlaude/), Ollama model/URL, context window size
  - llm.py — OllamaProvider with async streaming and title generation                                                                                          
  - db.py — SQLite CRUD via aiosqlite, uses a _connect() context manager that lazy-inits schema
  - server.py — FastAPI app, WebSocket handler (message routing, streaming, auto-title on first exchange)
  - cli.py — Typer app, single serve command, prints LAN IP                                                                                                    
   
  Frontend is static/index.html — all CSS + JS inline, uses Pretext via ESM CDN for text layout. PWA support via manifest.json + sw.js.                        
                                                         
  Key Conventions                                                                                                                                              
                                                         
  - No tests. Manual testing only.                                                                                                                             
  - No commits unless explicitly asked. Never stage, commit, or push without direct instruction.
  - Conservative versioning. Use v0.x for early builds, not v1.                                                                                                
  - Frontend is Vite + React + TypeScript in frontend/. Build with `cd frontend && npm run build`. Output goes to static/.
  - Dev mode: `cd frontend && npm run dev` (port 5173, proxies API/WS to :7474).
  - uv is the package manager (not pip directly).                                                                                                              
   
  --- 