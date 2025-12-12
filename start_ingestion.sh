#!/bin/bash
# Quick start script for Coloraria Ingestion Service

set -e

echo "========================================="
echo "Coloraria Ingestion Service"
echo "========================================="
echo ""

# Activate virtual environment
echo "✓ Activating virtual environment..."
source .venv/bin/activate

# Check dependencies
echo "✓ Checking dependencies..."
pip install -q python-dotenv 2>/dev/null || true

# Show help if no arguments
if [ $# -eq 0 ]; then
    echo ""
    echo "Usage: ./start_ingestion.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --law-id LAW_ID     Ingest a specific law (e.g., BOE-A-1978-31229)"
    echo "  --batch FILE        Ingest multiple laws from file (one ID per line)"
    echo "  --automatic         Fetch law IDs from BOE API automatically"
    echo "  --offset N          Start offset for BOE API pagination (default: 0)"
    echo "  --limit N           Maximum laws to fetch from API (default: 100)"
    echo "  --rollback LAW_ID   Rollback a previously ingested law"
    echo "  --dry-run           Parse only, don't write to database"
    echo "  --skip-embeddings   Skip embedding generation"
    echo "  --no-tracing        Disable Phoenix tracing"
    echo "  --output-json FILE  Write result to JSON file"
    echo ""
    echo "Examples:"
    echo "  ./start_ingestion.sh --law-id BOE-A-1978-31229"
    echo "  ./start_ingestion.sh --automatic --offset 0 --limit 50"
    echo "  ./start_ingestion.sh --rollback BOE-A-1978-31229"
    echo ""
    exit 0
fi

# Start the ingestion service
echo "✓ Starting ingestion..."
echo ""

python -m src.ingestion.main "$@"
