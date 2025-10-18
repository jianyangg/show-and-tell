# MCP Provider Overview

The `mcp_server/` package exposes the FastAPI runner through the Model Context Protocol so MCP-aware clients (Claude for Desktop, MCP Inspector, custom clients, etc.) can orchestrate recordings, plan synthesis, and automated runs.

## Quick Start

The MCP server uses **stdio transport** (standard input/output), which means it runs as a subprocess and communicates via JSON-RPC over stdin/stdout. This avoids port conflicts with your backend and is the standard way MCP servers operate.

## Module Layout

- `mcp_server/config.py` – environment-driven configuration loader (base URL, auth tokens, artifact directories).
- `mcp_server/runner_client.py` – async HTTP/WebSocket client that reuses backend schemas for request/response validation.
- `mcp_server/streams.py` – adapters that translate `/ws/runs/{id}` and `/ws/teach/{id}` payloads into MCP JSON streams.
- `mcp_server/tools.py` – registers MCP tools/streams (list plans, synthesize, start runs, capture screenshots, etc.).
- `mcp_server/main.py` – CLI entrypoint (`python -m mcp_server`) that starts the stdio MCP server.

## Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `RUNNER_BASE_URL` | Runner FastAPI base URL | `http://127.0.0.1:8000` |
| `RUNNER_API_KEY` / `RUNNER_API_KEY_PATH` | Inline bearer token or path to token file (JSON or plain text) | unset |
| `RUNNER_REPORT_DIR` | Root directory for generated run reports | `./reports` |
| `RUNNER_SCREENSHOT_DIR` | Output directory for screenshots captured via the MCP tool | `./reports` |

If `RUNNER_API_KEY_PATH` contains JSON, the loader searches for `token`, `api_key`, or `key` entries.

## Installation & Setup

### Prerequisites

1. **Python 3.9+** (Python 3.11 recommended)
2. **Backend running** on `http://localhost:8000` (or configured via `RUNNER_BASE_URL`)
3. **Official MCP SDK** installed:

```bash
pip install mcp
```

### Starting the MCP Server

The MCP server can be started as a Python module:

```bash
# From the project root
python -m mcp_server --log-level INFO

# Or with custom configuration
RUNNER_BASE_URL=http://localhost:8000 python -m mcp_server
```

**Note:** The MCP server uses **stdio transport**, not HTTP. It communicates via stdin/stdout and won't bind to any network port, so there's no conflict with your backend on port 8000.

## Integration Options

There are three primary ways to use the MCP server:

### Option 1: Claude for Desktop (Recommended for End Users)

Claude for Desktop is the easiest way to interact with your MCP server through a conversational interface.

**Setup:**

1. **Install Claude for Desktop** from [claude.ai/download](https://claude.ai/download)

2. **Configure the MCP server** by editing:
   - **macOS/Linux:** `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows:** `%AppData%\Claude\claude_desktop_config.json`

3. **Add your server configuration:**

```json
{
  "mcpServers": {
    "runner-mcp": {
      "command": "python3",
      "args": ["-m", "mcp_server"],
      "cwd": "/absolute/path/to/cursor-hackathon",
      "env": {
        "RUNNER_BASE_URL": "http://localhost:8000"
      }
    }
  }
}
```

**Important Notes:**
- Use **absolute paths** for `cwd`
- On Windows, use double backslashes (`\\`) or forward slashes (`/`)
- You may need the full path to `python3` (run `which python3` on macOS/Linux or `where python3` on Windows)

4. **Restart Claude for Desktop**

5. **Verify it's working:** Look for the 🔌 MCP icon in Claude indicating the server is connected

**Example Usage in Claude:**

```
You: "List all my saved plans"
Claude: [calls list_plans tool and shows results]

You: "Start run with plan ID 3361a5f6d1f64cafa86aed664a666f27 using variable greetingText='Hello!'"
Claude: [calls start_run tool and returns the runId]
```

### Option 2: MCP Inspector (Recommended for Testing & Development)

The MCP Inspector provides an interactive web UI for testing your MCP server and its tools.

**Setup:**

1. **Install Node.js** (if not already installed)

2. **Run the inspector:**

```bash
npx @modelcontextprotocol/inspector python3 -m mcp_server
```

3. **Open your browser** to the URL shown (usually `http://localhost:5173`)

4. **Test your tools** interactively through the web interface

**Benefits:**
- Visual interface for exploring available tools
- Can test tool calls with custom parameters
- Shows JSON request/response payloads
- Great for debugging and development

### Option 3: Programmatic Integration (For Custom Clients)

Build your own MCP client to integrate the runner into your application.

**Example Python Client:**

```python
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    # Configure the server
    server_params = StdioServerParameters(
        command="python3",
        args=["-m", "mcp_server"],
        env={
            "RUNNER_BASE_URL": "http://localhost:8000",
        },
    )

    # Connect to the server
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize
            await session.initialize()

            # List available tools
            tools = await session.list_tools()
            print(f"Available tools: {[t.name for t in tools.tools]}")

            # Call a tool
            result = await session.call_tool(
                "start_run",
                arguments={
                    "plan_id": "3361a5f6d1f64cafa86aed664a666f27",
                    "variables": {"greetingText": "Hello!"}
                }
            )
            print(f"Run started: {result}")

asyncio.run(main())
```

**Use Cases:**
- Custom automation scripts
- Integration with other tools and workflows
- Building web applications that leverage the runner
- CI/CD pipelines

## Viewing Runs in the Frontend

After starting a run via MCP, you can watch it live in the web frontend:

### Method 1: Using the "Connect to Run" Button (Easiest)

1. **Start your run via MCP** and note the returned `runId`
2. **Open the frontend** at http://localhost:5173
3. **Click "Connect to Run"** button in the header (blue outlined button)
4. **Paste the runId** and click "Connect"
5. **Watch it live!** You'll see:
   - Real-time browser viewport showing the automation
   - Console logs of each action
   - Step-by-step progress indicators
   - Current status updates

### Method 2: Direct WebSocket Connection (Advanced)

If you prefer programmatic access, connect directly to the WebSocket:

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/runs/YOUR_RUN_ID');

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log('Run event:', message);
};
```

## Tool Catalog

The provider registers the following tools and streaming endpoints:

- `list_plans(recording_id?)` – List stored automation plans
- `get_plan_details(plan_id)` – Get full plan definition with steps and variables
- `save_plan(plan_id, name, plan)` – Update a stored plan
- `list_recordings()` – List captured recordings
- `get_recording_bundle(recording_id)` – Download recording data (frames, events, audio)
- `synthesize_plan(recording_id, prompt, plan_name?)` – Generate plan from recording + prompt
- `start_run(plan_id, variables?)` – Execute a plan with optional variable substitution
- `abort_run(run_id)` – Stop a running plan
- `capture_screenshot(run_id, label?)` – Take screenshot during run execution
- Streams: `run_events(run_id)` and `teach_events(teach_id)` *(temporarily disabled in FastMCP migration)*

Each tool exposes JSON schema metadata so MCP clients can auto-discover arguments and results.

## Screenshot Handling

`capture_screenshot` persists base64 payloads to `RUNNER_SCREENSHOT_DIR/<run-id>/screenshot-<timestamp>.png`. When the backend returns a filename, the tool resolves it relative to the configured directory. Optional labels are written alongside the artifact (same base name with `.txt`).

## Troubleshooting

### Common Issues

**Issue: "Import mcp.server.fastmcp could not be resolved"**
- **Solution:** Install the official MCP SDK: `pip install mcp`
- Verify installation: `python3 -c "from mcp.server.fastmcp import FastMCP; print('OK')"`

**Issue: "Connection refused" or "Health check failed"**
- **Solution:** Ensure your backend is running on the configured URL (default: `http://localhost:8000`)
- Test backend: `curl http://localhost:8000/health`

**Issue: "TypeError: dataclass() got an unexpected keyword argument 'slots'"**
- **Solution:** You're using Python < 3.10. The codebase has been updated to support Python 3.9+
- Update your Python version or ensure you're using the latest code

**Issue: "400 Bad Request: Missing values for variables"**
- **Solution:** The plan requires variable values. When calling `start_run`, provide the `variables` parameter:
  ```json
  {
    "plan_id": "your-plan-id",
    "variables": {
      "variableName": "value"
    }
  }
  ```

**Issue: Run starts but frontend doesn't show it**
- **Solution:** The frontend needs to be manually connected to MCP-started runs:
  1. Note the `runId` from the MCP response
  2. Click "Connect to Run" in the frontend
  3. Paste the `runId` and connect

### Debug Logging

Enable detailed logging to troubleshoot issues:

```bash
# Start with DEBUG logging
python -m mcp_server --log-level DEBUG

# Or via environment variable
LOG_LEVEL=DEBUG python -m mcp_server
```

**Logs go to stderr** (not stdout, which is reserved for MCP JSON-RPC messages).

## Testing Your Setup

### Quick Test Script

Save this as `test_mcp.py` and run it to verify your setup:

```python
#!/usr/bin/env python3
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def test():
    server_params = StdioServerParameters(
        command="python3",
        args=["-m", "mcp_server"],
        env={"RUNNER_BASE_URL": "http://localhost:8000"},
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(f"✅ MCP server is working! Found {len(tools.tools)} tools:")
            for tool in tools.tools:
                print(f"  • {tool.name}")

asyncio.run(test())
```

Run it:
```bash
python3 test_mcp.py
```

Expected output:
```
✅ MCP server is working! Found 9 tools:
  • list_plans
  • get_plan_details
  • save_plan
  • list_recordings
  • get_recording_bundle
  • synthesize_plan
  • start_run
  • abort_run
  • capture_screenshot
```

## Validation Notes

The MCP server has been validated with the following workflow:

1. Started the backend with `scripts/run_demo.sh`
2. Created sample recordings and plans via the teach UI
3. Started the MCP server with `python -m mcp_server`
4. Connected via Claude for Desktop and MCP Inspector
5. Tested all tools: `list_plans`, `start_run`, `capture_screenshot`, etc.
6. Verified runs started via MCP can be viewed in the frontend using "Connect to Run"
7. Confirmed screenshot capture saves to `reports/<run-id>/` with optional labels
