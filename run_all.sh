#!/bin/bash

# Show and Tell - Run All Services
# This script starts all services needed for the application

# Color codes for pretty output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored messages
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to cleanup background processes on exit
cleanup() {
    print_info "Shutting down services..."
    kill $(jobs -p) 2>/dev/null
    print_success "All services stopped"
    exit 0
}

# Trap SIGINT and SIGTERM to cleanup
trap cleanup SIGINT SIGTERM

# Check prerequisites
print_info "Checking prerequisites..."

if ! command_exists python3; then
    print_error "Python 3 is not installed"
    exit 1
fi

if ! command_exists node; then
    print_error "Node.js is not installed"
    exit 1
fi

if ! command_exists yarn; then
    print_error "Yarn is not installed"
    exit 1
fi

print_success "Prerequisites check passed"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    print_warning "Virtual environment not found. Creating..."
    python3 -m venv venv
    source venv/bin/activate
    print_info "Installing Python dependencies..."
    pip install -r requirements.txt
    print_info "Installing Playwright browser..."
    python -m playwright install chromium
    print_success "Setup complete"
else
    print_info "Using existing virtual environment"
    source venv/bin/activate
fi

# Check if frontend dependencies are installed
if [ ! -d "frontend/node_modules" ]; then
    print_warning "Frontend dependencies not found. Installing..."
    cd frontend
    yarn install
    cd ..
    print_success "Frontend dependencies installed"
fi

# Start services
print_info "Starting all services..."
echo ""
print_info "Services will be available at:"
echo "  - Backend API:        ${GREEN}http://localhost:8000${NC}"
echo "  - Computer Use UI:    ${GREEN}http://localhost:5173${NC}"
echo "  - AI Debate Chat:     ${GREEN}http://localhost:9000${NC}"
echo "  - API Documentation:  ${GREEN}http://localhost:8000/docs${NC}"
echo ""
print_warning "Press Ctrl+C to stop all services"
echo ""

# Start Backend API
print_info "Starting Backend API (port 8000)..."
cd backend
uvicorn app.api:app --reload --log-level info > ../logs/backend.log 2>&1 &
BACKEND_PID=$!
cd ..
print_success "Backend API started (PID: $BACKEND_PID)"

# Wait a bit for backend to start
sleep 2

# Start Frontend
print_info "Starting Frontend (port 5173)..."
cd frontend
yarn dev > ../logs/frontend.log 2>&1 &
FRONTEND_PID=$!
cd ..
print_success "Frontend started (PID: $FRONTEND_PID)"

# Start Debate Server
print_info "Starting Debate Server (WebSocket port 8765)..."
cd chat
python debate_server.py > ../logs/debate.log 2>&1 &
DEBATE_PID=$!
cd ..
print_success "Debate Server started (PID: $DEBATE_PID)"

# Wait a bit for debate server to start
sleep 1

# Start Chat Frontend HTTP Server
print_info "Starting Chat Frontend (port 9000)..."
cd chat
python -m http.server 9000 > ../logs/chat-server.log 2>&1 &
CHAT_SERVER_PID=$!
cd ..
print_success "Chat Frontend started (PID: $CHAT_SERVER_PID)"

# Create logs directory if it doesn't exist
mkdir -p logs

echo ""
print_success "All services started successfully!"
echo ""
print_info "Logs are available in the 'logs/' directory"
print_info "To view logs in real-time:"
echo "  - Backend:       tail -f logs/backend.log"
echo "  - Frontend:      tail -f logs/frontend.log"
echo "  - Debate:        tail -f logs/debate.log"
echo "  - Chat Server:   tail -f logs/chat-server.log"
echo ""
print_warning "Press Ctrl+C to stop all services"
echo ""

# Wait for all background processes
wait
