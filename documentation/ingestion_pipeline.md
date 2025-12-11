# Ingestion Pipeline Architecture

> **Status**: Refactored (Dec 2024)  
> **Location**: `src/ingestion/`

## Overview

The ingestion pipeline processes Spanish legal documents (BOE - Boletín Oficial del Estado) through three concurrent stages:

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   CPU Pool      │     │   Network Pool   │     │   Disk Pool     │
│   (Parsers)     │────▶│   (Embedders)    │────▶│   (Writers)     │
│   5 workers     │     │   20 workers     │     │   2 workers     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
        │                       │                        │
        ▼                       ▼                        ▼
   Fetch XML              Generate              Save to Neo4j
   Parse to               Embeddings            Create Graph
   Domain Model           (Gemini API)          Nodes/Rels
```

## Directory Structure

```
src/ingestion/
├── main.py                     # CLI entry point
├── config.py                   # Environment configuration
├── models/
│   └── pipeline_models.py      # DTOs for pipeline stages
├── workers/
│   ├── cpu_worker.py           # Document fetching & parsing
│   ├── network_worker.py       # Embedding generation
│   └── disk_worker.py          # Neo4j persistence
├── services/
│   ├── resource_manager.py     # Resource lifecycle management
│   ├── dictionary_preloader.py # Pre-load Materia/Departamento nodes
│   └── bulk_reference_linker.py# Post-ingestion reference linking
├── orchestrator/
│   └── decoupled.py            # Producer-consumer orchestration
├── ingestion_context.py        # Rollback support for single-doc mode
└── result.py                   # Result types for single-doc mode
```

---

## Components

### 1. Pipeline Models (`models/pipeline_models.py`)

Data Transfer Objects that flow through the pipeline:

| Model | Purpose |
|-------|---------|
| `ParsedDocument` | Output of CPU stage: law_id, normativa, change_events, parse_duration |
| `EmbeddedDocument` | Output of Network stage: adds embed_duration |
| `DocumentResult` | Per-document result: success, nodes_created, etc. |
| `BatchIngestionResult` | Aggregate results for batch ingestion |

### 2. Workers

#### CPU Worker (`workers/cpu_worker.py`)
```python
def parse_document_sync(law_id: str) -> Optional[ParsedDocument]:
    """
    1. Fetch XML from BOE API via DataRetriever
    2. Parse to domain model via DataProcessor
    3. Return ParsedDocument with normativa tree
    """
```

#### Network Worker (`workers/network_worker.py`)
```python
async def generate_embeddings_scatter_gather(
    parsed: ParsedDocument,
    embedding_provider,
    embedding_cache,
    pool: ThreadPoolExecutor,
    scatter_chunk_size: int = 500
) -> EmbeddedDocument:
    """
    For large documents (>500 articles):
    1. SCATTER: Split articles into chunks
    2. PARALLEL: Process chunks concurrently
    3. GATHER: Wait for all, articles updated by reference
    """
```

#### Disk Worker (`workers/disk_worker.py`)
```python
def save_to_neo4j_sync(embedded: EmbeddedDocument, adapter) -> DocumentResult:
    """
    1. Save normativa tree via NormativaRepository
    2. Save change events via ChangeRepository
    3. Return DocumentResult with statistics
    """
```

### 3. Resource Manager (`services/resource_manager.py`)

Centralizes initialization of shared resources:

```python
class ResourceManager:
    async def initialize(self):
        # Neo4j connection + adapter
        self.connection = Neo4jConnection(...)
        self.adapter = Neo4jAdapter(self.connection)
        
        # Embedding cache (SQLite)
        self.embedding_cache = SQLiteEmbeddingCache("data/embeddings_cache.db")
        
        # Embedding provider (Gemini)
        self.embedding_provider = EmbeddingFactory.create("gemini", ...)
        
        # Vector indexer
        self.indexer = IndexerFactory.create("neo4j", ...)
```

### 4. Orchestrator (`orchestrator/decoupled.py`)

Coordinates the three worker pools using asyncio queues:

```python
class DecoupledIngestionOrchestrator:
    def __init__(self, cpu_workers=5, network_workers=20, disk_workers=2, ...):
        self._embed_queue = asyncio.Queue()  # CPU → Network
        self._save_queue = asyncio.Queue()   # Network → Disk
    
    async def run(self, law_ids: List[str]) -> BatchIngestionResult:
        # Stage 0: Initialize resources, preload dictionary
        # Stage 1: Launch worker pools, process documents
        # Stage 2: Create vector index
        # Stage 3: Bulk link references
```

---

## Usage

### Basic Batch Ingestion
```bash
python -m src.ingestion.main --batch data/laws.txt
```

### Skip Embeddings (Graph-Only Mode)
```bash
python -m src.ingestion.main --batch data/laws.txt --skip-embeddings
```
Bypasses the embedding generation stage entirely. Useful for:
- Fast graph construction testing
- Two-phase ingestion (graph first, embeddings later)

### Simulate Embeddings (No API Cost)
```bash
python -m src.ingestion.main --batch data/laws.txt --simulate
```
Uses fake embeddings for stress testing without Gemini API calls.

### Configuration Options
```bash
--cpu-workers N       # Default: 5
--network-workers N   # Default: 20  
--disk-workers N      # Default: 2
--scatter-chunk-size N # Default: 500 articles per embedding chunk
```

---

## Pipeline Stages

### Stage 0: Preparation
1. Initialize Neo4j connection
2. Drop existing vector index (will recreate at end)
3. Preload dictionary nodes (Materia, Departamento, Rango)

### Stage 1: Document Processing
- **CPU workers** fetch and parse documents → `embed_queue`
- **Network workers** generate embeddings → `save_queue`
- **Disk workers** save to Neo4j

### Stage 2: Post-Processing
1. Create vector index on Article.embedding
2. Bulk link cross-document references (REFERS_TO relationships)

---

## Error Handling

Each worker catches exceptions per-document:
```python
try:
    result = process_document(...)
except Exception as e:
    self._results.append(DocumentResult(
        law_id=law_id,
        success=False,
        error_message=str(e)
    ))
```

Failed documents don't stop the batch - final results show success/failure counts.

---

## Configuration

Environment variables (via `.env`):
```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
GOOGLE_API_KEY=your-gemini-key
PHOENIX_ENDPOINT=http://localhost:6006  # Optional tracing
```

---

## Rate Limiting

The pipeline includes a sliding window rate limiter for the Gemini API:

```python
# Default: 3000 articles per 60 seconds
rate_limiter = SlidingWindowRateLimiter(max_requests=3000, window_seconds=60.0)
```

**How it works:**
1. Before each embedding batch, `acquire(count)` is called
2. If capacity available, records usage and proceeds
3. If limit reached, blocks until oldest entries expire from window
4. Automatically prunes expired entries from history

The limiter is thread-safe and shared across all embedding workers.

---

## Performance Characteristics

| Document Size | Parse Time | Embed Time | Save Time |
|---------------|------------|------------|-----------|
| ~100 articles | ~2s | ~5s | ~3s |
| ~1000 articles | ~5s | ~30s | ~15s |
| ~3000 articles | ~10s | ~90s | ~45s |

With `--skip-embeddings`, total time is approximately parse_time + save_time.
