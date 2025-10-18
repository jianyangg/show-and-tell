# Run Control Loop

A minimal scaffolding around the Computer Use runner. The backend exposes HTTP + WebSocket APIs for starting a goal-driven run, streaming updates (including viewport frames), and aborting the run.

## Start a run

`POST http://localhost:8000/runs/start`

```json
{
  "runId": "demo-run",
  "goal": "Open example.com, scroll, and report the hero headline.",
  "startUrl": "https://example.com",
  "maxTurns": 8
}
```

`runId` is optional; if omitted the server generates one. The call returns `{ "runId": "..." }`.

## Stream run events

`WebSocket ws://localhost:8000/ws/runs/{runId}`

Events arrive as JSON objects. Implemented types today:

- `run_started` – initial acknowledgement with the run id, declared goal, and configuration.
- `runner_frame` – base64 PNG frames for the live viewport (same feed the bootstrap viewer renders) plus `cursor` metadata (`{ "x", "y" }`) when available.
- `turn_started` – snapshot of the current URL and screenshot before Gemini proposes the next tool calls.
- `actions_applied` – echo of the Computer Use function calls just executed.
- `turn_finished` – includes updated screenshot + URL after the actions along with the echoed summaries.
- `turn_failed` – emitted when a Playwright execution error occurs; includes the exception string.
- `run_finished` – marks completion (includes `ok` flag and optional `reason` such as `"completed"` or failure text).

## Abort a run

`POST http://localhost:8000/runs/{runId}/abort` – sets an abort flag, stops the screencast, and emits `run_finished` with `ok: false` once cleanup completes.

## Known gaps / next up

- Runs are purely goal-driven; RecordingBundle ingestion and plan synthesis still need to be implemented so the goal can be generated automatically from a demonstration.
- Assertions are no longer enforced; once plans are synthesized we will reintroduce declarative assertions aligned with the Plan DSL.
- No persistence layer yet; runs live in-memory only.
- Frontend integration remains a separate React TODO – the bootstrap canvas is still pointing at `/ws/runner`.
- Set `COMPUTER_USE_ENABLED=1` (and make sure `GEMINI_API_KEY` is defined) to let Gemini drive the goal via tool calls; otherwise `/runs/start` will finish immediately because no actions are returned.
- Event streaming now replays the entire history to each subscriber and drops runner frames down to the latest image, so reconnects/slow clients don’t stall the control channel.

## Debugging headless interaction flakes

- The runner now launches Chromium with a `1920x1080` viewport so Playwright's actionability checks succeed on pages that push content "below the fold" (e.g. `example.com`).
- If a step still times out, enable a trace by calling `context.tracing.start(...screenshots=True...)` inside `_chromium_page()` (temporary local edit) and inspect the saved `*.zip` via `playwright show-trace`.
- Drop in `page.screenshot(path="debug.png")` before the failing action to confirm what the headless browser is rendering.
