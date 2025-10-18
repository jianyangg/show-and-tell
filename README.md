# Show and Tell Runner

This repo contains the bootstrap slice of the Gemini Computer Use runner described in `PLAN.md`. It spins up a FastAPI backend that launches a headless Chromium session via Playwright, executes a simple plan, and streams viewport frames plus run events over WebSockets. A minimal HTML frontend renders the screencast for manual verification.

## Getting Started

- Python 3.11+
- Node (optional) if you want to use `npx wscat` for the run-event stream
- Playwright Chromium binaries (`python -m playwright install chromium`)
- Gemini access (`GEMINI_API_KEY` environment variable) if you want to turn on the Computer Use agent

### Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
python -m playwright install chromium
```

### Run the backend

```bash
uvicorn backend.app.api:app --reload
```

### Launch from the browser UI

Open `frontend/index.html`, point the **API Base** field at your FastAPI server, and follow the four-button loop:

1. **Start Record** – capture a teaching session (tab or cropped region).
2. **Stop Record** – upload the captured keyframes and markers to the backend.
3. **Synthesize Steps** – ask Gemini 2.5 Pro to convert the bundle into a plan.
4. **Run Steps** – execute the synthesized plan with Gemini Computer Use and watch the viewport render inside the canvas.

The console beneath the viewport shows the prompts/responses exchanged with Gemini 2.5 Pro and Gemini Computer Use so you can audit every turn.

While a run is active, any returned `safety_prompt` events display an allow/deny overlay. Declining halts the run immediately.

See `USER_MANUAL.md` for step-by-step instructions and troubleshooting tips.

### One-command demo helper

Use `scripts/run_demo.sh` to boot the backend and install dependencies inside `.venv`. The script leaves uvicorn running until you press `Ctrl+C`; perform the Record → Synthesize → Run loop from the browser.

### Enable Gemini Computer Use (optional)

Set your API key and flip on the agent flag before starting the server:

```bash
export GEMINI_API_KEY=...  # already present in your shell rc
export COMPUTER_USE_ENABLED=1
uvicorn backend.app.api:app --reload
```

When enabled, each turn sends a screenshot + goal context to Gemini 2.5 Computer Use, and the returned tool calls are executed via Playwright. The `actions_applied` events include the Computer Use function metadata so you can inspect what the model attempted.

## Current Scope

- Runs are plan-driven only; free-form goal execution has been removed.
- Recording bundles, plans, and runs are kept in-memory for fast iteration.
- Gemini 2.5 Pro powers plan synthesis, and Gemini Computer Use handles execution with a fixed 1440×900 viewport.
- `/runs/{id}/abort` signals the runner and short-circuits the current Playwright turn.

See `NOTES.md` for a short status log and `RUN_LOOP.md` for details on the execution APIs.
