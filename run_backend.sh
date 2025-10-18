#!/bin/bash

# Run Backend API only

# Activate virtual environment
source venv/bin/activate

# Start backend
echo "Starting Backend API on http://localhost:8000"
echo "API Documentation: http://localhost:8000/docs"
echo ""

cd backend
uvicorn app.api:app --reload --log-level info
