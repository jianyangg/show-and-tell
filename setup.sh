#!/bin/bash

# Show and Tell - Initial Setup Script
# Run this once to set up the development environment

# Color codes for pretty output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

echo ""
echo "=========================================="
echo "  Show and Tell - Setup Script"
echo "=========================================="
echo ""

# Check prerequisites
print_info "Checking prerequisites..."

if ! command_exists python3; then
    print_error "Python 3 is not installed. Please install Python 3.12+ first."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
print_success "Python $PYTHON_VERSION found"

if ! command_exists node; then
    print_error "Node.js is not installed. Please install Node.js 18+ first."
    exit 1
fi

NODE_VERSION=$(node --version)
print_success "Node.js $NODE_VERSION found"

if ! command_exists yarn; then
    print_error "Yarn is not installed. Installing yarn..."
    npm install -g yarn
fi

YARN_VERSION=$(yarn --version)
print_success "Yarn $YARN_VERSION found"

echo ""
print_info "Setting up Python virtual environment..."

# Create virtual environment if it doesn't exist
if [ -d "venv" ]; then
    print_warning "Virtual environment already exists. Skipping creation."
else
    python3 -m venv venv
    print_success "Virtual environment created"
fi

# Activate virtual environment
source venv/bin/activate
print_success "Virtual environment activated"

echo ""
print_info "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
print_success "Python dependencies installed"

echo ""
print_info "Installing Playwright browser (Chromium)..."
python -m playwright install chromium
print_success "Playwright browser installed"

echo ""
print_info "Installing frontend dependencies..."
cd frontend
yarn install
cd ..
print_success "Frontend dependencies installed"

echo ""
print_info "Creating logs directory..."
mkdir -p logs
print_success "Logs directory created"

echo ""
print_info "Checking for environment variables..."

if [ ! -f ".env" ]; then
    print_warning "No .env file found. Creating template..."
    cat > .env << 'EOF'
# Required API Keys
GEMINI_API_KEY=your_gemini_api_key_here
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here

# Optional
OPENAI_API_KEY=your_openai_api_key_here

# Configuration
COMPUTER_USE_ENABLED=true
RUNNER_VIEWPORT_WIDTH=1440
RUNNER_VIEWPORT_HEIGHT=900
RUNNER_MAX_TURNS=4
TEACH_FRAME_INTERVAL_SECONDS=1.0

# Logging
LOG_LEVEL=INFO
EOF
    print_warning "Created .env template. Please edit .env and add your API keys!"
else
    print_success ".env file already exists"
fi

echo ""
echo "=========================================="
print_success "Setup complete!"
echo "=========================================="
echo ""
print_info "Next steps:"
echo "  1. Edit .env file and add your API keys"
echo "  2. Run ${GREEN}./run_all.sh${NC} to start all services"
echo "  3. Or run individual services:"
echo "     - ${GREEN}./run_backend.sh${NC}  - Backend API only"
echo "     - ${GREEN}./run_frontend.sh${NC} - Frontend only"
echo "     - ${GREEN}./run_chat.sh${NC}     - Chat/Debate system only"
echo ""
print_info "Access points:"
echo "  - Computer Use UI:   ${GREEN}http://localhost:5173${NC}"
echo "  - AI Debate Chat:    ${GREEN}http://localhost:9000${NC}"
echo "  - API Docs:          ${GREEN}http://localhost:8000/docs${NC}"
echo ""
