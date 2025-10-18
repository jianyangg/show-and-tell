# Show and Tell

A multi-modal AI automation framework combining trainable computer use, AI debate system, and Model Context Protocol integration.

## Features

### 1. Trainable Computer Use
Teach AI by speaking and demonstrating - narrate instructions while performing browser actions, then synthesize your demonstrations into executable automation plans.

- **Teach**: Speak and narrate your intentions while demonstrating browser actions (clicks, typing, navigation)
- **Capture**: Records your voice instructions, screen actions, and audio transcription in real-time using ElevenLabs
- **Synthesize**: AI converts your multimodal demonstration into reusable, parameterizable plans using GPT-5
- **Execute**: Run synthesized plans with Gemini Computer Use for intelligent browser automation
- **Stream**: Real-time WebSocket updates with live viewport rendering

### 2. AI Debate/Chat System
Watch two Gemini AI models debate topics with animated avatars and text-to-speech.

- Dual Gemini models debating with full context tracking
- Live2D animated character models (Obama and Trump personas)
- ElevenLabs text-to-speech integration for realistic voices
- Real-time WebSocket streaming to browser
- Dynamic South Park-style background generation

### 3. MCP Server Integration
Model Context Protocol bridge exposing automation capabilities to Claude, Codex, and other AI tools.

- List and inspect synthesized plans
- Trigger plan synthesis from recordings
- Execute and monitor automation runs
- Capture screenshots and artifacts
- Event streaming for real-time updates

## Technology Stack

**Backend (Python):**
- FastAPI + Uvicorn (async HTTP & WebSocket server)
- Playwright (headless browser automation)
- OpenAI GPT-5 (plan synthesis from multimodal demonstrations)
- Google Gemini APIs (Computer Use for execution)
- Pydantic (data validation)
- SQLite (recording & plan storage)
- ElevenLabs TTS (text-to-speech)
- MCP SDK (Model Context Protocol)

**Frontend (TypeScript/React):**
- React 18.3 with Vite
- Material-UI (MUI)
- Zustand (state management)
- WebSocket client for real-time updates

**Chat/Visualization:**
- PIXI.js (2D WebGL renderer for animated sprites)
- WebSockets for real-time streaming
- Live2D models for character animation

## Prerequisites

- Python 3.12+
- Node.js 18+ and Yarn
- Chromium (installed via Playwright)
- API Keys:
  - `GEMINI_API_KEY` - Google Gemini API
  - `ELEVENLABS_API_KEY` - ElevenLabs TTS
  - `OPENAI_API_KEY` - OpenAI (optional)

## Installation

### 1. Set up Python virtual environment

```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browser
python -m playwright install chromium
```

### 2. Set up Frontend dependencies

```bash
cd frontend
yarn install
cd ..
```

### 3. Set up Chat dependencies

The `chat` directory contains both frontend (HTML/JS) and backend (Python) components. This is a hackathon-style setup - not the cleanest architecture but functional.

```bash
# Dependencies are already included in the root requirements.txt
# No additional setup needed
```

### 4. Configure environment variables

Create a `.env` file in the root directory:

```bash
# Required (I should have cleaned these up further)
GEMINI_API_KEY=your_gemini_api_key_here
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
COMPUTER_USE_ENABLED=1
PLAN_SYNTH_ENABLED=1
ENABLE_TRANSCRIPTION=1

# Optional
RUNNER_VIEWPORT_WIDTH=1440
RUNNER_VIEWPORT_HEIGHT=900
```

## Running the Application

### Quick Start (All Services)

Use the provided shell script to run all services in parallel:

```bash
chmod +x run_all.sh
./run_all.sh
```

This will start:
- Backend API on `http://localhost:8000`
- Frontend on `http://localhost:5173`
- Debate server on WebSocket `localhost:8765`
- Chat frontend on `http://localhost:9000`

### Manual Start (Individual Services)

If you prefer to run services individually in separate terminals:

#### Terminal 1: Backend API
```bash
source venv/bin/activate
cd backend
uvicorn app.api:app --reload
```

#### Terminal 2: Frontend
```bash
cd frontend
yarn dev
```

#### Terminal 3: Debate Server
```bash
source venv/bin/activate
cd chat
python debate_server.py
```

#### Terminal 4: Chat Frontend
```bash
cd chat
python -m http.server 9000
```

## Accessing the Application

Once all services are running:

- **Computer Use Frontend**: http://localhost:5173
  - Teach by speaking and demonstrating browser actions
  - Synthesize multimodal demonstrations into automation plans
  - Execute automated workflows with variable inputs

- **AI Debate Chat**: http://localhost:9000
  - Enter debate topics
  - Watch AI models debate with animations
  - View real-time transcripts

## MCP Server Setup

The MCP server exposes automation capabilities to Claude and other AI tools via the Model Context Protocol.

### Configuration

Add to your Claude Desktop config file (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "runner-mcp": {
      "command": "/path/to/your/show-and-tell/venv/bin/python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/your/show-and-tell",
      "env": {
        "RUNNER_BASE_URL": "http://127.0.0.1:8000",
        "PYTHONPATH": "/path/to/your/show-and-tell"
      }
    }
  }
}
```

**Important**: Replace `/path/to/your/show-and-tell` with your actual project path.

### Example Configuration

For reference, here's a complete example:

```json
{
  "mcpServers": {
    "runner-mcp": {
      "command": "/Users/jianyang/Documents/Documents - Jian Yang's MacBook Pro/cursor-hackathon/.venv/bin/python3.12",
      "args": ["-m", "mcp_server"],
      "cwd": "/Users/jianyang/Documents/Documents - Jian Yang's MacBook Pro/cursor-hackathon",
      "env": {
        "RUNNER_BASE_URL": "http://127.0.0.1:8000",
        "PYTHONPATH": "/Users/jianyang/Documents/Documents - Jian Yang's MacBook Pro/cursor-hackathon"
      }
    }
  }
}
```

### Available MCP Tools

Once configured, Claude can use these tools:

- `list_plans()` - List all synthesized automation plans
- `get_plan_details(plan_id)` - Inspect plan structure and variables
- `save_plan(plan)` - Create or update plans
- `list_recordings()` - Browse captured teaching sessions
- `synthesize_plan(recording_id, prompt)` - Generate plans from recordings
- `start_run(plan_id, variables)` - Execute automation
- `abort_run(run_id)` - Stop running automation
- `capture_screenshot()` - Get current viewport screenshot

## Project Structure

```
show-and-tell/
├── backend/              # FastAPI backend
│   ├── app/
│   │   ├── api.py       # Main API endpoints & WebSocket
│   │   ├── runner.py    # Automation execution engine
│   │   ├── synthesis.py # Plan synthesis from recordings
│   │   ├── storage.py   # SQLite storage layer
│   │   └── schemas.py   # Pydantic models
│   └── tests/
├── frontend/             # React TypeScript frontend
│   ├── src/             # Computer Use UI components
│   └── package.json
├── chat/                 # AI Debate system (frontend + backend)
│   ├── debate_server.py # WebSocket server for debates
│   ├── tts.py           # ElevenLabs TTS integration
│   ├── index.html       # Chat UI
│   ├── main.js          # PIXI.js sprite rendering
│   ├── runtime/         # Live2D character models
│   └── assets/          # Character sprites and backgrounds
├── mcp_server/           # Model Context Protocol bridge
│   ├── main.py          # MCP server entrypoint
│   ├── tools.py         # Tool definitions
│   └── runner_client.py # Backend API client
├── requirements.txt      # Python dependencies
├── run_all.sh           # Start all services script
└── README.md
```

## Key Workflows

### 1. Teaching/Recording

1. Start teaching session via frontend or API (`/teach/start`)
2. **Speak and narrate** your instructions while performing browser actions
   - Tell the AI what you're doing and why ("I'm clicking login because...")
   - Explain your intentions as you click, type, and navigate
   - Your voice provides context that pure actions cannot capture
3. System captures multimodal data:
   - **Audio**: Your voice narration and instructions
   - **Screen**: Screenshots at regular intervals (1 FPS default)
   - **Actions**: Clicks, typing, navigation events with timestamps
   - **Transcription**: Speech-to-text with word-level timestamps
4. Stop teaching session (`/teach/stop`)
5. Complete recording bundle (frames + events + audio + transcription) saved to SQLite database

### 2. Plan Synthesis
1. Select a recording
2. Provide optional prompt hints
3. GPT-5 converts multimodal demonstration (voice + actions + visuals) into structured plan
4. Variables extracted and normalized
5. Plan stored with metadata and visual checkpoints

### 3. Plan Execution
1. Select plan and provide variable values
2. Playwright browser launches (1440x900 viewport)
3. For each step:
   - Screenshot sent to Gemini Computer Use
   - AI returns tool calls (click, fill, navigate)
   - Actions executed via Playwright
   - Validation against assertions
4. Real-time streaming to WebSocket clients
5. Support for safety prompts and abort

### 4. AI Debate
1. Enter debate topic
2. Background image generated
3. Two Gemini models alternate turns
4. Text-to-speech via ElevenLabs
5. PIXI.js renders animated sprites
6. Real-time transcript display

## Development

### Backend Development

```bash
source venv/bin/activate
cd backend

# Run with auto-reload
uvicorn app.api:app --reload --log-level debug

# Run tests
pytest tests/
```

### Frontend Development

```bash
cd frontend

# Development server with hot reload
yarn dev

# Build for production
yarn build

# Preview production build
yarn preview
```

### Chat Development

```bash
source venv/bin/activate
cd chat

# Run debate server with debug logging
python debate_server.py

# Serve frontend
python -m http.server 9000
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Google Gemini API key | Required |
| `ELEVENLABS_API_KEY` | ElevenLabs TTS API key | Required |
| `OPENAI_API_KEY` | OpenAI API key (optional) | Required |
| `COMPUTER_USE_ENABLED` | Enable/disable Computer Use | `1` |
| `RUNNER_VIEWPORT_WIDTH` | Browser viewport width | `1440` |
| `RUNNER_VIEWPORT_HEIGHT` | Browser viewport height | `900` |
| `RUNNER_MAX_TURNS` | Max AI turns per step | `4` |
| `TEACH_FRAME_INTERVAL_SECONDS` | Recording frame rate | `1.0` |
| `RUNNER_CHECKPOINT_THRESHOLD` | Visual similarity threshold | `0.88` |

## API Documentation

Once the backend is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Troubleshooting

### Playwright Browser Issues
```bash
# Reinstall browser
python -m playwright install chromium

# Check browser installation
python -m playwright install --help
```

### Port Conflicts
If ports are already in use, modify:
- Backend: Change port in `uvicorn` command
- Frontend: Update `vite.config.ts`
- Chat: Change port in `python -m http.server` command
- Update `RUNNER_BASE_URL` in MCP config accordingly

### WebSocket Connection Issues
Ensure all services are running and check:
- Backend WebSocket: `ws://localhost:8000/teach/ws/{teach_id}`
- Debate WebSocket: `ws://localhost:8765`
- Frontend WebSocket client configuration

### Missing Dependencies
```bash
# Reinstall Python dependencies
pip install -r requirements.txt --force-reinstall

# Reinstall Node dependencies
cd frontend && yarn install --force
```

## License

[Your License Here]

## Contributors

David Wu Xingyu
Lim Jian Yang

## Acknowledgments

- Google Gemini for AI capabilities
- Anthropic Claude for MCP integration
- ElevenLabs for text-to-speech
- Playwright for browser automation
