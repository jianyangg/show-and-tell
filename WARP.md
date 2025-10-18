# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Development Commands

### Environment Setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
python -m playwright install chromium
```

### Running the Application
```bash
# Start backend server
uvicorn backend.app.api:app --reload

# One-command demo (starts server, launches sample run, prints WebSocket endpoint)
scripts/run_demo.sh

# Enable Gemini Computer Use (optional)
export GEMINI_API_KEY=your_key
export COMPUTER_USE_ENABLED=1
uvicorn backend.app.api:app --reload
```

### Testing
```bash
# Smoke test Playwright functionality
python test_playwright_example.py

# Manual API testing
curl -s -X POST http://localhost:8000/runs/start \
     -H 'Content-Type: application/json' \
     -d '{"goal":"Open example.com and scroll the page","startUrl":"https://example.com","maxTurns":6}'

# WebSocket monitoring (replace <runId> with actual ID)
npx wscat -c ws://localhost:8000/ws/runs/<runId>
```

## Architecture Overview

### Core Components
- **FastAPI Backend** (`backend/app/api.py`): HTTP/WebSocket server with CORS middleware
- **Run Manager** (`backend/app/run_manager.py`): In-memory run state tracking via `RunRegistry` and `RunState`
- **Computer Use Agent** (`backend/app/computer_use.py`): Gemini 2.5 Computer Use integration wrapper
- **Schema Definitions** (`backend/app/schemas.py`): Pydantic DTOs for API contracts
- **Frontend** (`frontend/index.html`): Minimal HTML screencast viewer with WebSocket connection

### Execution Flow
1. Client POSTs to `/runs/start` with goal/URL/max_turns
2. `RunRegistry` creates `RunState` and launches async task via `execute_run()`
3. Playwright launches headless Chromium with 1920x1080 viewport
4. Computer Use loop: screenshot → Gemini API → actions → Playwright execution
5. Events (`turn_started`, `actions_applied`, `run_finished`) stream over WebSocket
6. Chrome DevTools Protocol provides live viewport frames to WebSocket clients

### Key Data Flow
- **RunState**: Manages event queue (deque with 512 limit), frame sequences, cursor tracking
- **WebSocket Streams**: `/ws/runs/{id}` for run events, `/ws/runner` for raw viewport
- **Action Mapping**: Computer Use function calls → Playwright commands (click, type, scroll, navigate)

## Development Notes

### Viewport Configuration
- Fixed 1920x1080 viewport for consistent actionability checks
- Coordinates normalized from 0-999 range to actual pixel coordinates
- Screenshots captured via `page.screenshot(full_page=False)`

### Computer Use Integration
- Supports subset of predefined functions (click_at, type_text_at, navigate, scroll_document, etc.)
- Gemini responses filtered to `SUPPORTED_FUNCTIONS` list
- Base64 screenshot + text prompt sent to `gemini-2.5-computer-use-preview-10-2025`
- Async execution via `asyncio.to_thread()` wrapper

### Run Management
- Runs stored in-memory via `RunRegistry` (no persistence)
- Each run gets dedicated Playwright context/page
- Abort mechanism: sets `abort_event` + cancels asyncio task
- WebSocket clients can reconnect and replay buffered events

### Error Handling
- Playwright exceptions surface as `turn_failed` events
- WebSocket disconnections logged but don't crash runs
- Timeout mechanism for waiting on run creation (15 seconds)

## File Structure Context
- `backend/app/`: Core FastAPI application modules
- `frontend/`: Minimal HTML viewer (no build process required)
- `scripts/`: Helper script for quick demo launches
- `test_playwright_example.py`: Standalone smoke test
- Documentation files: `USER_MANUAL.md`, `TECH_STACK.md`, `RUN_LOOP.md`

## Environment Variables
- `GEMINI_API_KEY`: Required for Computer Use functionality
- `COMPUTER_USE_ENABLED`: Must be "1" to enable agent (defaults to disabled)
- `PORT`: Server port override for `run_demo.sh` (defaults to 8000)

## Coding Conventions
Match existing Python style: 4-space indentation, type hints on public methods, module-level loggers via `logging.getLogger(__name__)`. Use `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants. Pydantic models use `Field(..., alias=...)` for API field mapping. Prefer small async helpers with explicit returns and document algorithmic trade-offs with comments.
