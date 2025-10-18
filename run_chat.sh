#!/bin/bash

# Run Chat/Debate system (both server and frontend)

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Cleanup function
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down chat services...${NC}"
    kill $(jobs -p) 2>/dev/null
    echo -e "${GREEN}Chat services stopped${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# Activate virtual environment
source venv/bin/activate

echo "Starting AI Debate system..."
echo "  - Debate Server: WebSocket on localhost:8765"
echo "  - Chat Frontend: http://localhost:9000"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
echo ""

# Start debate server
cd chat
python debate_server.py &
DEBATE_PID=$!

# Wait a bit for server to start
sleep 2

# Start HTTP server for frontend
python -m http.server 9000 &
CHAT_SERVER_PID=$!

echo -e "${GREEN}Services started successfully!${NC}"
echo "Open http://localhost:9000 in your browser"
echo ""

# Wait for background processes
wait
