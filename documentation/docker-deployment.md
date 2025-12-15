# Docker Deployment Guide

This document covers the Docker deployment architecture for Coloraria, including all services, networking, and environment configuration.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                     coloraria_network (bridge)                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐           │
│  │   Neo4j     │     │  MariaDB    │     │    API      │           │
│  │   :7687     │◄────│   :3306     │◄────│   :8000     │           │
│  │  (graph)    │     │ (relational)│     │  (FastAPI)  │           │
│  └─────────────┘     └─────────────┘     └─────────────┘           │
│         ▲                                       ▲                   │
│         │ (populated by task)                   │                   │
│         │                                       │                   │
│         │           ┌─────────────┐             │                   │
│         └───────────│  Ingestion  │─────────────┘                   │
│                     │ (Python 3.14t)            (Neo4j Protocol)    │
│                     │   No-GIL    │                                 │
│                     └─────────────┘                                 │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Services & Tasks

| Component | Type | Image | Port | Purpose |
|-----------|------|-------|------|---------|
| **Neo4j** | Service | `neo4j:5-community` | 7474, 7687 | Graph database (laws, articles) |
| **MariaDB** | Service | `mariadb:10.11` | 3306 | Relational database (users, sessions) |
| **API** | Service | `Dockerfile.api` | 8000 | FastAPI REST/WebSocket server |
| **Ingestion** | **Task** | `Dockerfile.ingestion` | - | Ephemeral task to populate Neo4j before API starts |

---

## File Structure

```
Dockerfiles:
├── Dockerfile.api              # Python 3.12, FastAPI, LangGraph
└── Dockerfile.ingestion        # Python 3.14t (free-threaded), No-GIL

Compose Files:
├── docker-compose.infrastructure.yml   # Neo4j + MariaDB (creates network)
├── docker-compose.api.dev.yml          # API with source mounts
├── docker-compose.api.prod.yml         # API production
├── docker-compose.ingestion.dev.yml    # Ingestion with source mounts
└── docker-compose.ingestion.prod.yml   # Ingestion production
```

---

## Quick Start

### Development

```bash
# 1. Start infrastructure (creates coloraria_network)
docker compose -f docker-compose.infrastructure.yml up -d

# 2. Wait for databases to be healthy
docker compose -f docker-compose.infrastructure.yml ps

# 3. Start API (connects to network)
docker compose -f docker-compose.api.dev.yml up -d

# 4. Create initial user
docker compose -f docker-compose.api.dev.yml exec api python -m scripts.create_user admin password123

# 5. Run ingestion
docker compose -f docker-compose.ingestion.dev.yml run --rm ingestion --batch /app/data/laws.txt --decoupled
```

### Production

```bash
# 1. Start infrastructure
docker compose -f docker-compose.infrastructure.yml up -d

# 2. Build and start API
docker compose -f docker-compose.api.prod.yml up -d --build

# 3. Run ingestion
docker compose -f docker-compose.ingestion.prod.yml run --rm ingestion --batch /app/data/laws.txt --decoupled
```

---

## Environment Variables

Create a `.env` file in the project root:

```bash
# Required
GOOGLE_API_KEY=your-google-ai-key

# Database passwords
NEO4J_PASSWORD=your-neo4j-password
MARIADB_PASSWORD=your-mariadb-password
MARIADB_ROOT_PASSWORD=your-root-password

# Optional
DATABASE_TYPE=mariadb          # or sqlite
NEO4J_HEAP_SIZE=512m           # Neo4j memory
SHARED_DATA_PATH=./data        # Shared volume path

# Ingestion tuning
INGESTION_CPU_WORKERS=6
INGESTION_NETWORK_WORKERS=3
INGESTION_DISK_WORKERS=6
INGESTION_SCATTER_CHUNK_SIZE=1000

# Observability
PHOENIX_ENABLED=false
PHOENIX_ENDPOINT=http://phoenix:6006
```

---

## Networking

All services communicate via `coloraria_network`:

| Component | Creates Network | Joins Network |
|-----------|----------------|---------------|
| Infrastructure | ✅ `name: coloraria_network` | - |
| API | - | `external: true` |
| Ingestion | - | `external: true` |

**Important:** Always start infrastructure **first** to create the network.

---

## Development vs Production

| Feature | Development | Production |
|---------|-------------|------------|
| Source code | Mounted (`./src:/app/src:ro`) | Baked into image |
| Rebuild needed | Only for dependency changes | For any code change |
| Image tag | None | `coloraria-api:latest` |
| Restart policy | None | `unless-stopped` |
| Default passwords | Provided | Required in `.env` |

---

## Service Details

### API (`Dockerfile.api`)

- **Base:** `ghcr.io/astral-sh/uv:python3.12-bookworm-slim`
- **Dependencies:** `inference` group from `pyproject.toml`
- **Includes:** LangGraph, Phoenix observability, MariaDB drivers

```dockerfile
ENTRYPOINT ["python", "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Ingestion (`Dockerfile.ingestion`)

- **Base:** `ghcr.io/astral-sh/uv:python3.14-bookworm-slim`
- **Python:** 3.14t (free-threaded, No-GIL)
- **Dependencies:** `ingestion` group from `pyproject.toml`

```dockerfile
ENV PYTHON_GIL=0  # Enables free-threading
ENTRYPOINT ["python", "-m", "src.ingestion.main"]
```

#### Verify No-GIL:
```bash
docker compose -f docker-compose.ingestion.dev.yml run --rm --entrypoint python ingestion -c "import sys; print(sys._is_gil_enabled())"
# Expected: False
```

---

## Data Persistence

| Service | Volume | Content |
|---------|--------|---------|
| Neo4j | `neo4j_data` | Graph database |
| MariaDB | `mariadb_data` | Users, sessions, checkpoints |
| API/Ingestion | `./data:/app/data` | Embedding cache (SQLite) |

### Backup

```bash
# Neo4j
docker exec coloraria-neo4j-1 neo4j-admin database dump neo4j --to-path=/data/backups

# MariaDB
docker exec coloraria-mariadb-1 mysqldump -u coloraria_user -p coloraria > backup.sql
```

---

## Common Commands

```bash
# View logs
docker compose -f docker-compose.api.dev.yml logs -f api

# Shell into container
docker compose -f docker-compose.api.dev.yml exec api bash

# Stop all services
docker compose -f docker-compose.infrastructure.yml down
docker compose -f docker-compose.api.dev.yml down

# Remove volumes (⚠️ deletes data)
docker compose -f docker-compose.infrastructure.yml down -v
```

---

## Troubleshooting

### "Network coloraria_network not found"

Start infrastructure first:
```bash
docker compose -f docker-compose.infrastructure.yml up -d
```

### "Connection refused" to Neo4j/MariaDB

Wait for health checks:
```bash
docker compose -f docker-compose.infrastructure.yml ps
# Both should show "healthy"
```

### API can't connect to MariaDB

Verify network connectivity:
```bash
docker compose -f docker-compose.api.dev.yml exec api ping mariadb
```

### Ingestion GIL still enabled

Ensure `PYTHON_GIL=0` is set and using correct Python:
```bash
docker compose -f docker-compose.ingestion.dev.yml run --rm --entrypoint "uv" ingestion run python -c "import sys; print(sys._is_gil_enabled())"
```
