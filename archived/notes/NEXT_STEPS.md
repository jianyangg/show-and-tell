## Voice-Controlled MCP Automation

- Set up speech-to-text (Whisper, Deepgram, etc.) to convert voice commands into transcripts for your agent.
- Host an MCP-compatible agent that can parse the transcript into actionable intents such as “load plan Alpha, set product_name=Sparkling Water, start run.”
- Implement an MCP tool provider that wraps the FastAPI endpoints:
  - `list_plans` → `GET /plans`
  - `get_plan_details` → `GET /plans/{plan_id}`
  - `start_run` → `POST /runs/start`
  - optional: recordings and synthesis helpers if you want full automation.
- Ensure the agent retrieves plan metadata and variable schemas so it can match voice intents to the correct plan and fill variables.
- Orchestrate the loop: voice → transcript → agent reasoning → MCP tool calls → backend run kickoff → frontend updates via the existing WebSockets.
- Test the flow end-to-end with a known plan to verify the UI reflects the run triggered through MCP.

## Voice Call Shopping Flow (Twilio + ElevenLabs + MCP)

- Twilio streams caller audio (“help me purchase seaweed”) to ElevenLabs STT for transcription, then plays back an ElevenLabs TTS acknowledgement (“I’m on it. I’ll send you a message or email when I’m done.”).
- Forward the transcript to the MCP-capable agent. It locates the taught shopping plan via `list_plans`/`get_plan_details`, fills variables (e.g., `item=seaweed`), and calls `start_run`.
- The runner executes the taught Playwright shopping workflow; the frontend reflects progress through `/ws/runs/{id}`.
- Before checkout, the agent invokes a custom MCP `capture_screenshot` tool, packages the screenshot, and sends a yes/no confirmation to the user (SMS/email).
- On approval, the agent resumes or continues the run; on denial, it calls `abort_run`.
- ElevenLabs TTS delivers final status to the caller, and the stored screenshot/report is shared over the chosen channel.
