# Manual Plan Replay Smoke Test

This checklist walks through the record → plan → replay loop using the demo iframe and the new plan-driven runner.

## Prerequisites

- Backend dependencies installed (`pip install -r backend/requirements.txt`) and Playwright Chromium downloaded (`python -m playwright install chromium`).
- Optional: fresh virtualenv activated.

## Steps

1. **Launch the API server**
   ```bash
   uvicorn backend.app.api:app --reload
   ```
   Leave this terminal running; it exposes `http://localhost:8000`.

2. **Open the demo UI**
   - In a separate shell, start a lightweight web server from the repo root:
     ```bash
     python -m http.server 9000
     ```
   - Visit `http://localhost:9000/frontend/index.html` in a Chromium-based browser.

3. **Record an interaction**
   - In the “Demo Recorder” panel, click **Start Recording** and interact with the embedded iframe (e.g., scroll `example.com`, click a link, type into the search box).
   - Stop the recording; confirm the timeline, events, and metadata populate in the review panel.

4. **Synthesize a plan**
   - Ensure the generated recording is selected, then click **Synthesize Plan**.
   - Wait for the status badge to show the stored plan name and step count. Verify the step list and variable table render.

5. **Run the plan**
   - Click **Run Plan**. The event log should emit `run_started`, followed by `step_started`, `actions_applied`, `assert_passed/failed`, and `step_finished` entries.
   - Observe the plan step list: the active step is highlighted during execution, then marked green (pass) or red (fail) with attempt details.

6. **Confirm completion**
   - Ensure a `run_finished` event arrives with `ok: true`.
   - The viewport canvas should stream the Playwright session with cursor overlay updates tagged by `runner_frame` events carrying the active `stepId`.

7. **Optional abort sanity check**
   - Start another plan run, then trigger **Reset Run** to hit `/runs/{runId}/abort`. Confirm the event log records the abort, active step highlight clears, and the run ends with `run_finished` reason `aborted`.

## Expected Results

- The plan execution uses the stored selectors/vars, and assertions pass for the recorded flow.
- WebSocket events include step metadata (`step_started`, `step_finished`, `assert_*`) and `runner_frame` payloads include `stepId`.
- The front-end event log renders human-readable summaries, and the plan review list reflects per-step status.
