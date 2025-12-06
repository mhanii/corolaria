#!/bin/bash
# Quick start script for Coloraria API

set -e

echo "========================================="
echo "Coloraria API - Quick Start"
echo "========================================="
echo ""

# Activate virtual environment
echo "✓ Activating virtual environment..."
source .venv/bin/activate

# Install dependencies if needed
echo "✓ Checking dependencies..."
pip install -q fastapi uvicorn[standard] 2>/dev/null || true

# Start the API server
echo "✓ Starting API server..."
echo ""
echo "Server will be available at:"
echo "  - API: http://localhost:8000"
echo "  - Docs: http://localhost:8000/docs"
echo "  - Health: http://localhost:8000/health"
echo ""
echo "Press Ctrl+C to stop"
echo ""

uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
