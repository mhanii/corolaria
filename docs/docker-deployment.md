# Docker Deployment for Coloraria Ingestion Pipeline

This guide covers deploying the ingestion pipeline as a Docker container using Python 3.14t (free-threaded) for maximum parallelism.

## Quick Start

```bash
# 1. Copy environment file and configure
cp .env.example .env
# Edit .env with your NEO4J_PASSWORD and GOOGLE_API_KEY

# 2. Build and run with Docker Compose
docker compose -f docker-compose.ingestion.yml up --build

# 3. Run ingestion for a specific law
docker compose -f docker-compose.ingestion.yml run ingestion --law-id BOE-A-1978-31229
```

## Verification

```bash
# Verify Python 3.14t (free-threaded)
docker compose -f docker-compose.ingestion.yml run --rm ingestion python -VV

# Verify GIL is disabled (CRITICAL - must return False)
docker compose -f docker-compose.ingestion.yml run --rm ingestion python -c "import sys; print(f'GIL Active: {sys._is_gil_enabled()}')"
```

## Configuration

All configuration is via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j connection URI |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | - | Neo4j password |
| `GOOGLE_API_KEY` | - | Google AI API key for embeddings |
| `INGESTION_CPU_WORKERS` | `5` | Parser thread pool size |
| `INGESTION_NETWORK_WORKERS` | `20` | Embedding thread pool size |
| `INGESTION_DISK_WORKERS` | `2` | Neo4j writer thread pool size |
| `INGESTION_SCATTER_CHUNK_SIZE` | `500` | Articles per embedding batch |
| `PHOENIX_ENABLED` | `false` | Enable observability tracing |

## CLI Usage

```bash
# Single law ingestion
docker compose run ingestion --law-id BOE-A-1978-31229

# Batch ingestion from file
docker compose run ingestion --batch /app/data/laws.txt --decoupled

# Dry run (parse only, no DB writes)
docker compose run ingestion --law-id BOE-A-1978-31229 --dry-run

# Rollback a law
docker compose run ingestion --rollback BOE-A-1978-31229
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Docker Network                        │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────┐       ┌─────────────────────────────┐  │
│  │   Neo4j     │◄──────│   Ingestion Container       │  │
│  │  :7687      │       │   Python 3.14t (No-GIL)     │  │
│  └─────────────┘       │   ├── CPU Pool (parsers)    │  │
│                        │   ├── Network Pool (embed)  │  │
│                        │   └── Disk Pool (writers)   │  │
│                        └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## Troubleshooting

### GIL still enabled
If `sys._is_gil_enabled()` returns `True`, the container may have fallen back to standard Python. Rebuild with:
```bash
docker compose -f docker-compose.ingestion.yml build --no-cache
```

### C extension compilation errors
Ensure `build-essential` and `python3-dev` are installed in the Dockerfile.

### Neo4j connection refused
Wait for Neo4j to be healthy before running ingestion:
```bash
docker compose -f docker-compose.ingestion.yml up neo4j -d
# Wait for healthy status
docker compose -f docker-compose.ingestion.yml run ingestion --law-id BOE-A-1978-31229
```
