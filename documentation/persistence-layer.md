# Database Persistence Layer

This document covers the database persistence layer for Coloraria, which supports both **SQLite** (for simple local development) and **MariaDB** (default, recommended for production and concurrent access).

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                     Application                         │
└────────────────────────┬────────────────────────────────┘
                         │
        ┌────────────────▼────────────────┐
        │     get_database_connection()   │
        │        (connection_factory)     │
        └────────────────┬────────────────┘
                         │
           ┌─────────────┴─────────────┐
           │                           │
    ┌──────▼──────┐           ┌────────▼────────┐
    │   SQLite    │           │    MariaDB      │
    │  (Adapter)  │           │  (Connection)   │
    └──────┬──────┘           └────────┬────────┘
           │                           │
    ┌──────▼──────┐           ┌────────▼────────┐
    │ SQLite DB   │           │    MariaDB      │
    │ (file-based)│           │  (Docker/Cloud) │
    └─────────────┘           └─────────────────┘
```

## Quick Start

### Default (MariaDB)
```bash
# Start MariaDB container
docker compose -f docker-compose.api.dev.yml up -d mariadb

# Set password and run
export MARIADB_PASSWORD=coloraria_pass
export MARIADB_URI=mysql+pymysql://coloraria_user:coloraria_pass@localhost:3306/coloraria
python -m uvicorn src.api.main:app --reload
```

### Development (SQLite - optional fallback)
```bash
# Override to use SQLite
export DATABASE_TYPE=sqlite
python -m uvicorn src.api.main:app --reload
```

---

## Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `DATABASE_TYPE` | Database backend: `sqlite` or `mariadb` | `sqlite` | No |
| `MARIADB_URI` | Full connection string (overrides individual vars) | - | No |
| `MARIADB_HOST` | MariaDB host | `mariadb` (Docker) | No |
| `MARIADB_PORT` | MariaDB port | `3306` | No |
| `MARIADB_DATABASE` | Database name | `coloraria` | No |
| `MARIADB_USER` | Database user | `coloraria_user` | No |
| `MARIADB_PASSWORD` | Database password | - | **Yes** (for MariaDB) |

### URI Format
```
mysql+pymysql://user:password@host:port/database
```

Example:
```bash
export MARIADB_URI="mysql+pymysql://coloraria_user:mypass@localhost:3306/coloraria"
```

---

## Configuration File

Database settings can also be configured in `config/config.yaml`:

```yaml
database:
  type: "mariadb"  # or "sqlite"
  
  sqlite:
    path: "data/coloraria.db"
  
  mariadb:
    host: "mariadb"
    port: 3306
    database: "coloraria"
    user: "coloraria_user"
    password: ""  # Use MARIADB_PASSWORD env var instead
    pool_size: 10
    pool_recycle: 3600
```

> **Note**: Environment variables take precedence over config file settings.

---

## Database Tables

The schema includes 7 core tables:

| Table | Purpose |
|-------|---------|
| `users` | User accounts, authentication, token balances |
| `conversations` | Chat conversation metadata |
| `messages` | Individual messages within conversations |
| `message_citations` | Legal citations attached to assistant messages |
| `feedback` | User feedback (like/dislike) on responses |
| `surveys` | Beta testing surveys for token refills |
| `schema_version` | Schema versioning for migrations |

### Auto-Initialization

Tables are created automatically on first connection. No manual scripts needed for fresh deployments.

```
[MariaDB] Checking database schema...
[MariaDB] Creating tables...
[MariaDB] Created 7 tables
```

---

## Production Deployment with Docker

### 1. Docker Compose Setup

Use `docker-compose.api.prod.yml`:

```bash
docker compose -f docker-compose.api.prod.yml up -d
```

This starts:
- **MariaDB** container (port 3306, persistent volume)
- **API** container (depends on MariaDB health check)

### 2. Required Environment Variables

Create a `.env` file or set in your deployment platform:

```bash
# Required
MARIADB_PASSWORD=your_secure_password
MARIADB_ROOT_PASSWORD=your_root_password

# Optional (defaults work for Docker)
DATABASE_TYPE=mariadb
MARIADB_HOST=mariadb
```

### 3. Health Check

MariaDB includes a health check that the API waits for:

```yaml
healthcheck:
  test: ["CMD", "healthcheck.sh", "--connect", "--innodb_initialized"]
  interval: 10s
  timeout: 5s
  retries: 5
```

### 4. Data Persistence

MariaDB data is stored in a Docker volume:

```yaml
volumes:
  mariadb_data:
```

To backup:
```bash
docker exec coloraria-mariadb-1 mysqldump -u coloraria_user -p coloraria > backup.sql
```

---

## Migrating from SQLite to MariaDB

If you have existing SQLite data:

```bash
# 1. Ensure MariaDB is running
docker compose -f docker-compose.api.dev.yml up -d mariadb

# 2. Run migration script
MARIADB_URI="mysql+pymysql://coloraria_user:coloraria_pass@localhost:3306/coloraria" \
python scripts/migrate_to_mariadb.py

# 3. Verify with CRUD tests
MARIADB_URI="mysql+pymysql://coloraria_user:coloraria_pass@localhost:3306/coloraria" \
python scripts/test_mariadb_crud.py
```

The migration script:
- Creates a backup of SQLite (`data/coloraria.db.backup.<timestamp>`)
- Migrates all tables with data integrity checks
- Handles duplicates gracefully (idempotent)

---

## Adding New Tables

### Step 1: Add to Schema

Edit `src/infrastructure/database/mariadb_schema.py`:

```python
TABLES = [
    # ... existing tables ...
    """
    CREATE TABLE IF NOT EXISTS my_new_table (
        id VARCHAR(36) PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        created_at DATETIME NOT NULL,
        INDEX idx_my_new_table_name (name)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]
```

### Step 2: Add SQLite Schema

Edit `src/infrastructure/sqlite/base.py`:

```python
SCHEMA_SQL = """
-- ... existing tables ...

CREATE TABLE IF NOT EXISTS my_new_table (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_my_new_table_name ON my_new_table(name);
"""
```

### Step 3: Create Repository

Create `src/infrastructure/database/mariadb_my_repository.py`:

```python
class MariaDBMyRepository:
    def __init__(self, connection):
        self._conn = connection
    
    def create(self, name: str) -> MyModel:
        id = str(uuid.uuid4())
        self._conn.execute(
            "INSERT INTO my_new_table (id, name, created_at) VALUES (:p0, :p1, :p2)",
            (id, name, datetime.now())
        )
        return MyModel(id=id, name=name)
```

### Step 4: Register in Factory

Edit `src/infrastructure/database/repository_factory.py`:

```python
def get_my_repository(connection) -> MyRepository:
    db_type = os.getenv("DATABASE_TYPE", "sqlite")
    if db_type == "mariadb":
        from .mariadb_my_repository import MariaDBMyRepository
        return MariaDBMyRepository(connection)
    else:
        from src.infrastructure.sqlite.my_repository import MyRepository
        return MyRepository()
```

### Step 5: Bump Schema Version

In `mariadb_schema.py`, increment the version:

```python
SCHEMA_VERSION = 5  # Was 4
```

---

## Key Differences: SQLite vs MariaDB

| Feature | SQLite | MariaDB |
|---------|--------|---------|
| **Placeholders** | `?` | `:p0, :p1, ...` |
| **Data Types** | TEXT, INTEGER | VARCHAR, INT, DATETIME, JSON |
| **Auto-increment** | AUTOINCREMENT | AUTO_INCREMENT |
| **JSON** | TEXT (stored as string) | JSON (native type) |
| **Boolean** | INTEGER (0/1) | TINYINT(1) |
| **Concurrency** | WAL mode (limited) | Full MVCC |
| **Connection** | File-based | Connection pool |

### Concurrency

MariaDB uses **atomic UPDATE with WHERE clause** for token operations:

```sql
UPDATE users 
SET available_tokens = available_tokens - :amount 
WHERE id = :user_id AND available_tokens >= :amount
```

This prevents race conditions that can occur with SQLite's read-then-write pattern.

---

## LangGraph Checkpointer

The LangGraph checkpointer also supports both backends:

| Backend | Checkpointer | Package |
|---------|--------------|---------|
| SQLite | `SqliteSaver` | `langgraph-checkpoint-sqlite` |
| MariaDB | `PyMySQLSaver` | `langgraph-checkpoint-mysql[pymysql]` |

The checkpointer is selected automatically based on `DATABASE_TYPE`.

---

## Troubleshooting

### "Can't connect to MySQL server on 'mariadb'"

When running from host (not Docker), use `localhost`:
```bash
export MARIADB_HOST=localhost
# or
export MARIADB_URI="mysql+pymysql://user:pass@localhost:3306/coloraria"
```

### "Table doesn't exist"

Tables are auto-created on connection. If this fails:
1. Check MariaDB is running: `docker compose ps`
2. Check logs: `docker compose logs mariadb`
3. Manual schema creation: `python scripts/create_mariadb_schema.py`

### Connection Pool Exhausted

Increase pool size in config:
```yaml
mariadb:
  pool_size: 20  # Default is 10
```

---

## File Reference

| File | Purpose |
|------|---------|
| `src/infrastructure/database/interface.py` | Abstract `DatabaseConnection` interface |
| `src/infrastructure/database/mariadb_connection.py` | MariaDB connection with SQLAlchemy pooling |
| `src/infrastructure/database/sqlite_adapter.py` | SQLite adapter for the interface |
| `src/infrastructure/database/connection_factory.py` | Factory that selects backend |
| `src/infrastructure/database/mariadb_schema.py` | MariaDB schema and auto-init |
| `src/infrastructure/database/repository_factory.py` | Repository factory |
| `src/infrastructure/database/checkpointer.py` | LangGraph checkpointer factory |
| `scripts/migrate_to_mariadb.py` | SQLite → MariaDB migration |
| `scripts/test_mariadb_crud.py` | CRUD verification tests |
