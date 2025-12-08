# Ingestion Pipeline TODO

## High Priority

- [ ] **Parallel Embedding Generation**: Use `asyncio.gather()` for concurrent batch requests to Gemini API (2-3x faster)
- [ ] **Batch Neo4j Writes**: Use `UNWIND` for batch operations (nodes in groups of 500+) (5-10x faster)
- [ ] **Connection Pooling**: Single Neo4j connection pool shared across steps
- [ ] **Embedding Retry Logic**: Exponential backoff + retry for transient Gemini errors

## Medium Priority

- [ ] **Validation Layer**: Early validation of raw data structure before processing
- [ ] **Persist Change Events**: `change_events` are collected but never persisted to Neo4j - implement persistence

## Low Priority

- [ ] **Transaction Batching**: Explicit transactions with checkpoints for partial recovery
- [ ] **Idempotency Check**: Check for existing Normativa before ingestion, offer update mode
