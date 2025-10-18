#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8000}"
cd "$ROOT_DIR"

if [ ! -d .venv ]; then
  python -m venv .venv
fi

source .venv/bin/activate

python -m pip install --quiet --disable-pip-version-check -r backend/requirements.txt
python -m playwright install chromium >/dev/null 2>&1

UVICORN_BIN="$(python -c "import uvicorn,sys;print(uvicorn.__file__.rsplit('/',2)[0]+'/__main__.py')")"

# Launch uvicorn in-process so we can trap it cleanly.
python -m uvicorn backend.app.api:app --host 127.0.0.1 --port "$PORT" &
SERVER_PID=$!

cleanup() {
  if kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

for _ in {1..30}; do
  if curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null; then
    break
  fi
  sleep 0.5
done

cat <<EOF
Backend ready on http://127.0.0.1:${PORT}

1. Open frontend/index.html in your browser.
2. Click "Start Record" to capture a teaching session.
3. Stop the recording, synthesize steps, then run the plan.

Press Ctrl+C to stop the server.
EOF

wait "$SERVER_PID"
