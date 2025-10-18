# Repository Guidelines

## Project Structure & Module Organization
The FastAPI runner lives in `backend/app`; `api.py` exposes HTTP+WS endpoints, `synthesis.py` wraps Gemini 2.5 Pro for plan generation, and `runner.py` drives the Playwright + Computer Use loop. In-memory stores reside in `storage.py`. The screencast viewer is `frontend/index.html`. `scripts/run_demo.sh` boots the backend and leaves it running so you can perform a manual Record → Synthesize → Run loop. `test_playwright_example.py` remains a Playwright smoke helper.

## Build, Test, and Development Commands
- `python -m venv .venv && source .venv/bin/activate`: create and enter the local virtualenv.
- `pip install -r backend/requirements.txt`: install backend and automation dependencies.
- `python -m playwright install chromium`: fetch the headless browser required by the runner.
- `uvicorn backend.app.api:app --reload`: start the API server with autoreload on port 8000.
- `scripts/run_demo.sh`: spin up the server and leave it running; launch the four-button flow from `frontend/index.html`.
- `python test_playwright_example.py`: run the Playwright smoke script that exercises example.com.
- `USER_MANUAL.md`: end-user instructions for launching runs from `frontend/index.html`.

## Coding Style & Naming Conventions
Match the existing Python style: 4-space indentation, type hints on public methods, and module-level loggers via `logging.getLogger(__name__)`. Keep functions and variables in `snake_case`, classes in `PascalCase`, and constants (e.g., viewport sizes) in `UPPER_SNAKE_CASE`. Pydantic models should expose API field names through `Field(..., alias=...)`, mirroring the FastAPI responses. Favor small async helpers with explicit returns so log output stays predictable. Document tricky branches with brief comments, justify algorithmic trade-offs, and annotate expected complexity so the code reads like a top-tier computer science exam submission.

## Testing Guidelines
Fast feedback comes from `scripts/run_demo.sh`, which validates `/health`, triggers a run, and prints the WebSocket endpoint to monitor. Use `python test_playwright_example.py` for targeted Playwright assertions; name new checks `test_<feature>.py` and keep them beside the script until a larger suite lands. Attach screenshots (`debug_before_click.png`, etc.) when documenting failures.

## Commit & Pull Request Guidelines
Follow the Conventional Commits style already in history (`feat:`, `fix:`, `chore:`). Each commit should focus on one concern and leave the repo runnable via `scripts/run_demo.sh`. For pull requests, include a concise summary, linked issues or plan references, verification notes (commands executed, run IDs observed), and screenshots or logs when UI or screencast output changes. Flag any new environment variables or secrets that reviewers must set (`GEMINI_API_KEY`, `COMPUTER_USE_ENABLED`).

## Security & Configuration Tips
Keep API keys in your shell profile or a local `.env` ignored by Git. Leave `COMPUTER_USE_ENABLED` unset unless you have Gemini access; when disabled, `/runs/start` will return without Gemini-driven actions. Redact websocket payloads that contain base64 frames or user URLs before sharing logs.
