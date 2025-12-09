# Retrieval System Documentation

## Overview

The retrieval system provides flexible, multi-strategy search capabilities for legal articles with comprehensive visualization and benchmarking tools.

## Architecture

```
User Query
    ↓
RetrievalService (Orchestrator)
    ↓
Strategy Selection
    ↓
┌────────────────┬──────────────────┬──────────────────┬─────────────────┬────────────┐
│ Vector Search  │ Keyword Search   │ Hybrid Search    │ Graph Traversal │ LLM Query  │
└────────────────┴──────────────────┴──────────────────┴─────────────────┴────────────┘
    ↓
SearchResult Objects
    ↓
ResultVisualizer
```

## Quick Start

### Basic Usage

```python
from src.domain.services.retrieval_service import RetrievalService
# ... initialize service ...

# Simple search
results = service.search("freedom of speech", strategy="hybrid", top_k=10)

# Compare strategies
multi_results = service.multi_strategy_search("derechos fundamentales", top_k=5)

# Benchmark
benchmark = service.benchmark_strategies(["query1", "query2"])
```

### CLI Usage

```bash
# Single query
python scripts/test_retrieval.py --query "libertad de expresión" --strategy hybrid

# Compare strategies
python scripts/test_retrieval.py --query "derechos fundamentales" --compare-strategies

# Benchmark mode
python scripts/test_retrieval.py --benchmark

# Interactive mode
python scripts/test_retrieval.py --interactive
```

## Retrieval Strategies

### 1. Vector Search (`vector`) within RAG
- **Method**: Semantic similarity using embeddings
- **Enrichment**:
    - **Validity Checking**: Automatically checks if citations are outdated. If an article has a `NEXT_VERSION`, it "hops" to the latest version while noting the discrepancy.
    - **Reference Expansion**: Automatically fetches articles that the result `REFERS_TO` (up to 3 levels) to provide context.
- **Best for**: Conceptual queries, synonyms, related concepts
- **Example**: "individual freedoms" → finds articles about rights even without exact match

### 2. Keyword Search (`keyword`)
- **Method**: Text pattern matching (case-insensitive)
- **Best for**: Exact terms, article numbers, specific phrases
- **Example**: "Artículo 14" or "constitutional"

### 3. Hybrid Search (`hybrid`) ⭐ Recommended
- **Method**: Combines vector (70%) + keyword (30%)
- **Best for**: Most general searches
- **Features**: 
  - Deduplicates overlapping results
  - Weighted scoring
  - Configurable weights

### 4. Graph Traversal (`graph`)
- **Method**: Navigate graph structure
- **Modes**:
  - `structure`: Get all articles in Title/Chapter/Book
  - `versions`: Get historical versions of an article
  - `subject`: Get articles by Materia (subject matter)
- **Example**: All articles in "Título I"

### 5. LLM Query (`llm`) 
- **Status**: Placeholder for future implementation
- **Planned**: Query reformulation, intent extraction

## RAG Enrichment (`ChunkEnricher`)

The RAG pipeline includes an automatic enrichment step implemented in `RAGCollector`:

1.  **Validity Checking**:
    *   For every retrieved chunk, checks if `(article)-[:NEXT_VERSION]->(newer)`.
    *   If a newer version exists, it traverses to the **latest** version.
    *   The LLM context receives the latest text but is informed that the retrieval found an older version.

2.  **Reference Expansion (`REFERS_TO`)**:
    *   For search results, the system looks for outgoing `REFERS_TO` relationships.
    *   Fetches linked articles (up to 3) to provide immediate context for definitions/references.

## API Reference

### RetrievalService

#### `search(query, strategy, top_k, **kwargs)`
Execute a search with specific strategy.

**Parameters**:
- `query` (str): Search query
- `strategy` (str): Strategy name ("vector", "keyword", "hybrid", "graph", "llm")
- `top_k` (int): Number of results (default: 10)

**Returns**: `List[SearchResult]`

#### `search_with_context(query, strategy, top_k, context_window, **kwargs)`
Search and include surrounding articles.

**Parameters**:
- `context_window` (int): Number of surrounding articles to include

#### `multi_strategy_search(query, strategies, top_k, **kwargs)`
Run query across multiple strategies for comparison.

**Returns**: `Dict[str, List[SearchResult]]`

#### `benchmark_strategies(queries, strategies, top_k, **kwargs)`
Benchmark performance across queries.

**Returns**: `List[BenchmarkResult]`

### SearchResult

Value object representing a search result.

**Fields**:
- `article_id`: Unique identifier (String)
- `article_number`: Display number (e.g., "14")
- `article_text`: Full article text
- `normativa_title`: Parent normativa title
- `score`: Relevance score (0.0-1.0)
- `strategy_used`: Which strategy produced this result
- `context_path`: Hierarchical path
- `metadata`: Additional data

**Methods**:
- `get_context_path_string()`: Human-readable path
- `get_preview(max_length)`: Text preview

## Configuration

### Environment Variables

```bash
# Required
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
GOOGLE_API_KEY=your_gemini_api_key

# Optional
QDRANT_URL=http://localhost:6333
```

### Embedding Configuration

For **queries**, use `RETRIEVAL_QUERY` task type:
```python
EmbeddingConfig(
    model_name="models/gemini-embedding-001",
    dimensions=768,
    task_type="RETRIEVAL_QUERY"  # ← Important for queries
)
```

For **documents** (ingestion), use `RETRIEVAL_DOCUMENT`:
```python
EmbeddingConfig(
    task_type="RETRIEVAL_DOCUMENT"  # ← For indexing
)
```

## Visualization

### Result Display

```python
from src.utils.result_visualizer import ResultVisualizer

# Print results
ResultVisualizer.print_results(results, max_preview=200)

# Compare strategies
ResultVisualizer.compare_strategies(multi_results, top_k=5)

# Show benchmark
ResultVisualizer.print_benchmark(benchmark_results)

# Export
ResultVisualizer.export_results(results, "output/results.json", format="json")
```

## Examples

### Example 1: Find Articles About a Concept

```python
# Semantic search for "freedom of speech"
results = service.search(
    query="libertad de expresión",
    strategy="vector",
    top_k=5
)

for result in results:
    print(f"Article {result.article_number}: {result.score:.4f}")
    print(result.get_preview(150))
```

### Example 2: Compare Search Strategies

```python
# Compare how different strategies handle the same query
multi_results = service.multi_strategy_search(
    query="derechos fundamentales",
    strategies=["vector", "keyword", "hybrid"],
    top_k=5
)

ResultVisualizer.compare_strategies(multi_results)
```

### Example 3: Benchmark Performance

```python
# Test queries
queries = [
    "libertad de expresión",
    "igualdad ante la ley",
    "Artículo 14"
]

# Run benchmark
benchmark = service.benchmark_strategies(
    queries=queries,
    strategies=["vector", "keyword", "hybrid"],
    top_k=10
)

ResultVisualizer.print_benchmark(benchmark)
```

### Example 4: Graph Traversal

```python
# Get all articles in a Title
results = service.search(
    query="titulo_1_id",  # Structure ID
    strategy="graph",
    mode="structure",
    structure_type="Título"
)

# Get article versions
versions = service.search(
    query="article_id",
    strategy="graph",
    mode="versions"
)
```

## Performance Tips

1. **Use Hybrid for Most Cases**: Balances semantic understanding with exact matches
2. **Adjust Weights**: Modify `vector_weight` in hybrid search based on your use case
3. **Cache Queries**: Query embeddings can be cached for repeated searches
4. **Use top_k Wisely**: Fetching too many results increases latency
5. **Context Window**: Only use when needed; adds extra database queries

## Troubleshooting

### No Results Found
- Check if vector index exists: `CREATE VECTOR INDEX article_embeddings ...`
- Verify embeddings are stored on Article nodes
- Try keyword search to confirm data exists

### Slow Vector Search
- Index may not be created or warmed up
- Check Neo4j logs for index status
- Consider smaller `top_k` or batch queries

### Poor Result Quality
- Try different strategies
- Adjust hybrid weights
- Use `compare_strategies` to see differences
- Check query embedding quality

## Future Enhancements

- **LLM Query Strategy**: Full implementation with Gemini Pro
- **Result Caching**: Cache frequent queries
- **Fulltext Index**: Neo4j fulltext index for keyword search
- **Relevance Feedback**: User feedback to improve ranking
- **Faceted Search**: Filter by date, normativa, subject

## File Structure

```
src/
├── domain/
│   ├── interfaces/
│   │   └── retrieval_strategy.py
│   ├── value_objects/
│   │   └── search_result.py
│   └── services/
│       └── retrieval_service.py
├── ai/
│   └── rag/
│       ├── vector_search_strategy.py
│       ├── keyword_search_strategy.py
│       ├── hybrid_search_strategy.py
│       ├── graph_traversal_strategy.py
│       └── llm_query_strategy.py
├── infrastructure/
│   └── graphdb/
│       └── adapter.py (with retrieval methods)
└── utils/
    └── result_visualizer.py

scripts/
└── test_retrieval.py
```
