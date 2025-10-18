# Runner Viewport Bootstrap

A minimal vertical slice that streams Chromium frames from the backend to a browser canvas. Use this to validate the Computer Use runner loop before the full app exists.

## Backend

### Install deps

Create and activate a virtualenv, then install requirements:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
python -m playwright install chromium
```

### Run

```bash
uvicorn backend.app.api:app --reload
```

Key endpoints:

- `POST /recordings/start` / `POST /recordings/{id}/stop` for the teaching capture bundle.
- `POST /plans/synthesize` to produce the compact plan DSL.
- `POST /runs/start` / `POST /runs/{id}/abort` to control the executor.
- `ws://localhost:8000/ws/runs/{id}` to stream viewport frames and step events.
- `GET /health` for a quick readiness check.

## Frontend viewer

Open `frontend/index.html` in a browser (no build tooling required for the bootstrap). Follow the **Start Record → Stop Record → Synthesize Steps → Run Steps** sequence to capture, generate, and execute a plan. The canvas renders both recorded frames (for review) and live run output.

## Verifying it works

1. Start the FastAPI app and confirm `GET http://localhost:8000/health` returns `{ "ok": true }`.
2. Open the frontend file in your browser.
3. Click the four buttons in order. After **Run Steps**, the viewport should show Gemini Computer Use interacting with your chosen start URL. Step events appear alongside the canvas.
4. Stop the server and confirm the frontend reports that the connection closed.

To adjust the initial navigation, set the **Start URL** input before launching the run.
