# Mlaude (v0.1)

Mlaude is a personal AI agent that runs entirely locally, built to be private, minimal, and beautiful. 

It provides an ultra-lightweight web UI that connects to local LLM backends (like Ollama) offering a seamless, ad-free, and privacy-focused alternative to cloud assistants. Features a responsive modern design with automatic light/dark mode and native mobile web-app support.

## Features
- **Privacy First:** All data is stored locally. No telemetry.
- **Beautiful UI:** Polished, vanilla CSS interface without the bloat of frontend frameworks.
- **Auto Light & Dark Mode:** Integrates seamlessly with your system `prefers-color-scheme`.
- **Real-Time Status:** Displays connection and "Thinking..." status when talking to the LLM backend.
- **Mobile Support:** Mobile-friendly sidebar and swipe interactions.

## Setup & Running

This project uses modern Python tools (`uv` / `pyproject.toml`). 

1. Ensure you have Python >= 3.11 installed.
2. Install dependencies (e.g. using `uv sync` or `pip install -e .`).
3. Run the app:

```bash
uv run mlaude
```

By default it will act as a server on `http://0.0.0.0:7474`. You can access it locally in your browser.

## Tech Stack
- Frontend: Vanilla HTML, CSS, and JS (No heavy build steps needed).
- Backend: FastAPI, Uvicorn, Python.
- LLM Interface: Ollama.

## License
MIT
