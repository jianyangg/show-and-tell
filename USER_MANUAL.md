# User Manual

This guide walks through the Record → Synthesize → Run loop for the Gemini Computer Use prototype after the plan-only overhaul.

## Prerequisites

- Python 3.11+
- Playwright Chromium binaries (`python -m playwright install chromium`)
- Backend dependencies (`pip install -r backend/requirements.txt`)
- Gemini API access:
  ```bash
  export GEMINI_API_KEY=your_api_key
  export COMPUTER_USE_ENABLED=1
  export PLAN_SYNTH_ENABLED=1
  ```
- Backend server running from the repo root:
  ```bash
  uvicorn backend.app.api:app --reload
  ```

## Record a Teaching Session

1. Open `frontend/index.html` directly in your browser. No dev server is required.
2. In the **API Base** field, confirm the URL of the FastAPI backend (e.g. `http://localhost:8000`).
3. Optionally set **Start URL**—the executor will navigate there before running the synthesized steps.
4. Click **Start Record**. The browser will prompt for screen/tab capture. Pick the tab you want to teach.
   - Chrome 122+ supports Region Capture; if available, the recorder crops to the viewport canvas automatically. Otherwise it captures the entire tab.
   - While recording, press ⌘M / Ctrl+M to drop timeline markers for important beats.
5. Perform the task manually. The recorder snapshots frames at ~1 fps and stores markers locally.
6. Click **Stop Record** when finished. The UI uploads frames + markers to `/recordings/{id}/stop` and enables plan synthesis.
   - Check the **Console** under the viewport to confirm the backend acknowledged the upload.

## Synthesize a Plan

1. Click **Synthesize Steps**. The frontend POSTs to `/plans/synthesize` using the latest `recordingId`.
2. When synthesis succeeds, the **Plan Steps** list populates with the compact DSL (`navigate`, `click_at`, `type_text_at`).
3. Review each step to confirm assertions and variable placeholders look correct. The recorder state remains in memory; re-run synthesis if you want a fresh plan.
   - The console logs the Gemini 2.5 Pro prompt and raw JSON response for every synthesis call.

## Execute with Gemini Computer Use

1. Click **Run Steps**. The frontend POSTs to `/runs/start` with `{ planId, startUrl? }` and opens a WebSocket at `/ws/runs/{id}`.
2. The viewport canvas streams screenshots at ~5–10 fps while Gemini Computer Use issues low-level actions. Current steps highlight in the plan sidebar.
3. If Gemini returns a `safety_prompt`, an overlay appears with Allow / Deny buttons. Runs resume only after you explicitly choose one.
4. When the run completes (success, failure, or abort) the status line updates and the overlay hides automatically.
   - Every turn emits `[ComputerUse prompt]` / `[ComputerUse response]` lines in the console so you can audit the calls and the returned tool actions.

## Reviewing the Recording

- **Timeline thumbnails** — Click any frame button to preview the captured screenshot in the main canvas.
- **Markers** — The list under the timeline shows ⌘M / Ctrl+M markers with timestamps. Markers are included in the synthesis prompt.
- Recordings stay in memory for this session. Start a new recording to reset the timeline before the next walkthrough.

## Interrupting a Run

- Send an abort from a terminal if needed:
  ```bash
  curl -X POST http://localhost:8000/runs/<runId>/abort
  ```
- Declining a safety prompt also halts the current run (the backend marks it as failed).

## Troubleshooting

- **No frames after Start Record** — Most browsers require the captured tab to stay focused. Keep the recorder page visible while teaching.
- **Plan synthesis fails immediately** — Ensure `PLAN_SYNTH_ENABLED=1` and `GEMINI_API_KEY` are exported. Errors surface in the backend logs.
- **Run never progresses** — Verify `COMPUTER_USE_ENABLED=1`. Without the Computer Use flag the executor rejects runs because it cannot call the model.
- **WebSocket drops** — The frontend auto-reconnects on the next run start. Check console logs for network errors if it disconnects mid-run.

For deeper debugging, open the browser DevTools console. Every REST call and WebSocket message is logged, including the full payloads for timeline frames and plan events.
