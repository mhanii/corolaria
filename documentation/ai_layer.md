# AI & Reasoning Layer

## Overview
This layer provides the "intelligence" of the Legal Agent. It handles semantic understanding through embeddings and (planned) reasoning through Large Language Models (LLMs).

**Location**: `src/ai/`

## 1. Embeddings
*   **Purpose**: To convert legal text into vector representations for semantic search.
*   **Provider**: Google Gemini (`gemini-embedding-001`).
*   **Configuration**:
    *   **Dimensions**: 768.
    *   **Task Type**: `RETRIEVAL_DOCUMENT` (optimized for indexing documents).
*   **Factory Pattern**: `EmbeddingFactory` (`src/ai/embeddings/factory.py`) allows switching providers (e.g., from Gemini to OpenAI or HuggingFace) without changing the pipeline logic.
*   **Caching**: `JSONFileCache` (`src/ai/embeddings/json_cache.py`) stores embeddings locally to minimize API costs and latency during development/re-indexing.

## 2. Indexing (Vector Database)
*   **Location**: `src/ai/indexing/`
*   **Purpose**: To store and query the generated vectors.
*   **Backends**:
    *   **Neo4j Vector Index**: Integrated directly into the Graph DB. Allows hybrid queries (Graph + Vector).
    *   **Qdrant** (Planned/Partial): Specialized Vector DB for high-performance similarity search.

## 3. Reasoning & RAG (Planned)
*   **Goal**: To answer user questions using the indexed laws.
*   **Retrieval Augmented Generation (RAG)** Workflow:
    1.  **User Query**: "What is the penalty for X?"
    2.  **Retrieval**:
        *   Convert query to vector.
        *   Search Vector DB for most similar Articles.
        *   Traverse Graph to get surrounding context (e.g., the Chapter title).
    3.  **Generation**:
        *   Send Query + Retrieved Articles to LLM (Gemini Pro).
        *   LLM generates a natural language answer citing the specific articles.
