# Quick Start Guide

## First Time Setup

```bash
# Run the setup script (only needed once)
./setup.sh

# Edit .env file and add your API keys
nano .env  # or use your preferred editor
```

## Running the Application

### Option 1: Run Everything (Recommended)

```bash
./run_all.sh
```

This starts all services:
- Backend API: http://localhost:8000
- Computer Use UI: http://localhost:5173
- AI Debate Chat: http://localhost:9000

### Option 2: Run Individual Services

```bash
# Backend only
./run_backend.sh

# Frontend only
./run_frontend.sh

# Chat/Debate only
./run_chat.sh
```

### Option 3: Manual Commands

#### Terminal 1 - Backend
```bash
source venv/bin/activate
cd backend
uvicorn app.api:app --reload
```

#### Terminal 2 - Frontend
```bash
cd frontend
yarn dev
```

#### Terminal 3 - Debate Server
```bash
source venv/bin/activate
cd chat
python debate_server.py
```

#### Terminal 4 - Chat Frontend
```bash
cd chat
python -m http.server 9000
```

## Required Environment Variables

Create a `.env` file in the root directory:

```bash
GEMINI_API_KEY=your_gemini_api_key_here
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
```

## Access Points

Once running, access:

- **Computer Use**: http://localhost:5173
  - Teach by speaking and demonstrating browser actions
  - Synthesize multimodal demonstrations into automation plans
  - Execute workflows with variable inputs

- **AI Debate**: http://localhost:9000
  - Enter debate topics
  - Watch AI models debate with animations

- **API Documentation**: http://localhost:8000/docs
  - Swagger UI for backend API

## MCP Integration (Optional)

To use with Claude Desktop, add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "runner-mcp": {
      "command": "/path/to/show-and-tell/venv/bin/python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/show-and-tell",
      "env": {
        "RUNNER_BASE_URL": "http://127.0.0.1:8000",
        "PYTHONPATH": "/path/to/show-and-tell"
      }
    }
  }
}
```

Replace `/path/to/show-and-tell` with your actual project path.

## Troubleshooting

### "Port already in use"
Kill processes using the ports:
```bash
# Kill process on port 8000 (backend)
lsof -ti:8000 | xargs kill -9

# Kill process on port 5173 (frontend)
lsof -ti:5173 | xargs kill -9

# Kill process on port 9000 (chat)
lsof -ti:9000 | xargs kill -9
```

### "Module not found"
Reinstall dependencies:
```bash
source venv/bin/activate
pip install -r requirements.txt --force-reinstall
cd frontend && yarn install --force
```

### "Playwright browser not found"
```bash
source venv/bin/activate
python -m playwright install chromium
```

## Logs

When using `run_all.sh`, logs are saved to:
- `logs/backend.log`
- `logs/frontend.log`
- `logs/debate.log`
- `logs/chat-server.log`

View logs in real-time:
```bash
tail -f logs/backend.log
tail -f logs/frontend.log
tail -f logs/debate.log
```
