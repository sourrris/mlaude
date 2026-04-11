# TODO

## Remaining

- Make the database story explicit and production-ready.
  Today the app runs locally with the default SQLAlchemy local database path, while `MLAUDE_DATABASE_URL` remains optional. If PostgreSQL is going to be the standard local setup, add migrations and document that path clearly.

- Improve mobile and narrow-screen source browsing.
  The current source sidebar is strongest on desktop. A smaller-screen drawer or sheet version would make citations and supporting context usable on laptops and mobile widths.

- Tighten Ollama failure and recovery UX.
  The app already surfaces runtime-unavailable states, but it should better guide the user through missing models, refused connections, and model refresh/retry flows.

- Add file management polish.
  Library and chat file upload work, but there is still room for rename, delete, replace, and clearer scoping controls between current-session files and shared library files.

- Add packaging and local startup convenience.
  The repo still starts as separate backend and frontend dev processes. A simple local up script would make first-run and repeat-run smoother.

## Deferred

- Multi-user accounts, auth, teams, orgs, billing, and admin surfaces
- Agents, projects, galleries, editors, or other higher-order workspace abstractions
- Deep research flows
- External connector platforms
- Custom MCP, OpenAPI, or OAuth-based tools
- Paid model providers and cloud model routing
- Web search provider integration beyond the current local-first scope
- Docker-first deployment assumptions
- SaaS marketing pages and non-app product surfaces

## Nice To Have Later

- Stronger retrieval ranking and chunk merging
- Background ingestion jobs for larger local libraries
- Better session search and filtering
- Export/import for chats and local knowledge files
- Single-command local dev boot for frontend, backend, and runtime checks
