# Ingestion Pipeline TODO

## High Priority

- [ ] **Parallel Embedding Generation**: Use `asyncio.gather()` for concurrent batch requests to Gemini API (2-3x faster)
- [x] **Batch Neo4j Writes**: Already uses `UNWIND` for batch operations via APOC
- [x] **Connection Pooling**: Single Neo4j connection shared across steps
- [x] **Embedding Retry Logic**: Exponential backoff + retry for transient Gemini errors

## Medium Priority

- [ ] **Validation Layer**: Early validation of raw data structure before processing
- [x] **Persist Change Events**: Change events saved to Neo4j with article-level relationships

## Low Priority

- [ ] **Transaction Batching**: Explicit transactions with checkpoints for partial recovery


