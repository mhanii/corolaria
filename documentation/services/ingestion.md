# Ingestion Pipeline (`IngestionService`)

## Overview
The **Ingestion Pipeline** is the mechanism by which Coloraria acquires knowledge. It transforms unstructured or semi-structured legal texts into a structured Knowledge Graph.

**Location**: `src/ingestion/main.py` (Service Entry Point)

## Service Architecture

The ingestion process has been refactored into a service-oriented architecture with the following features:
*   **CLI Interface**: Easy-to-use command line tools.
*   **Transaction Management**: Automatic rollback on failure.
*   **Observability**: Integrated Phoenix tracing for performance and error tracking.
*   **Dry Run Mode**: Parse-only mode for validation without database writes.

## Usage

Run the ingestion service via the module:

```bash
# Ingest a specific law
python -m src.ingestion.main --law-id BOE-A-1978-31229

# Dry run (no database writes)
python -m src.ingestion.main --law-id BOE-A-1978-31229 --dry-run

# Manual Rollback (delete law and its tree)
python -m src.ingestion.main --rollback BOE-A-1978-31229
```

## Pipeline Steps

The pipeline executes the following steps sequentially, orchestrated by `src/application/pipeline/doc2graph.py`:

### 1. Data Retrieval (`DataRetriever`)
*   **Source**: `src/application/pipeline/data_ingestion.py`
*   **Function**: Connects to the BOE (Boletín Oficial del Estado) API.
*   **Input**: A Law ID (e.g., `BOE-A-1978-31229`).
*   **Output**: Raw XML/JSON response containing text and metadata.

### 2. Data Processing (`DataProcessor`)
*   **Source**: `src/application/pipeline/data_processing.py`
*   **Function**: Parses raw data into a Domain Model.
*   **Key Logic**:
    *   **Compound Article Handling**: Splits multi-article text blocks (e.g., "Artículos 1 a 5").
    *   **Tree Construction**: Builds a `NormativaCons` tree: `Normativa -> Libro -> Título -> Capítulo -> Artículo`.
    *   **Metadata**: Extracts dates, validity status, and derogations.

### 3. Graph Construction (`GraphConstruction`)
*   **Source**: `src/application/pipeline/graph_construction.py`
*   **Function**: Persists the Domain Model into Neo4j.
*   **Optimization**: Structural nodes (Books, Titles) are **not created**. Only `Normativa` (root) and `Article` (leaf) nodes exist. Hierarchy is preserved in the article's `path` property.

### 4. Embedding Generation (`EmbeddingGenerator`)
*   **Source**: `src/application/pipeline/embedding_step.py`
*   **Function**: Generates and stores vector embeddings for articles.
*   **Process**:
    1.  **Context Building**: Creates rich text representations including hierarchy path.
    2.  **Hashing & Caching**: Avoids redundant API calls.
    3.  **API Call**: Google Gemini (`gemini-embedding-001`).
    4.  **Storage**: 768-dimension vector stored on `ArticleNode`.

## Rollback Mechanism

The service uses `IngestionContext` to track created nodes.
*   **Auto-Rollback**: If an exception occurs, all nodes created during the session are deleted.
*   **Manual Rollback**: Can reference a law ID to clean up a specific ingestion.
*   **Scope**: Deletes `Normativa` and its `Article` tree. Preserves shared nodes like `Materia`, `Departamento`, `Rango`.

