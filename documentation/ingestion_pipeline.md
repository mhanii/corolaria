# Ingestion Pipeline (`Doc2Graph`)

## Overview
The **Ingestion Pipeline** is the mechanism by which Coloraria acquires knowledge. It transforms unstructured or semi-structured legal texts into a structured Knowledge Graph.

**Location**: `src/application/pipeline/doc2graph.py`

## Pipeline Steps

The pipeline executes the following steps sequentially:

### 1. Data Retrieval (`DataRetriever`)
*   **Source**: `src/application/pipeline/data_ingestion.py`
*   **Function**: Connects to the BOE (Boletín Oficial del Estado) API.
*   **Input**: A Law ID (e.g., `BOE-A-1978-31229` - The Spanish Constitution).
*   **Output**: Raw XML/JSON response containing the law's text and metadata.
*   **Key Component**: `BOEHTTPClient` handles the async HTTP requests.

### 2. Data Processing (`DataProcessor`)
*   **Source**: `src/application/pipeline/data_processing.py`
*   **Function**: Parses the raw data into a Domain Model.
*   **Key Logic**:
    *   **Compound Article Handling**: Detects when a single block of text refers to multiple articles (e.g., "Artículos 1 a 5") and splits them into individual logical units. This is critical for granular citation and retrieval.
    *   **Tree Construction**: Builds a `NormativaCons` object, which is a tree structure:
        `Normativa -> Libro -> Título -> Capítulo -> Artículo`
    *   **Metadata Extraction**: Extracts publication dates, validity status (`vigencia`), and relationships (derogations).

### 3. Embedding Generation (`EmbeddingGenerator`)
*   **Source**: `src/application/pipeline/embedding_step.py`
*   **Function**: Enriches the `ArticleNode`s with semantic vectors.
*   **Process**:
    1.  **Context Building**: Generates a rich text representation for each article, including its full hierarchy path (Context) and its validity status.
    2.  **Hashing & Caching**: Checks `data/embeddings_cache.json` using a SHA256 hash of the context to avoid redundant API calls.
    3.  **API Call**: If not cached, sends the text to Google Gemini (`gemini-embedding-001`).
    4.  **Assignment**: Stores the resulting vector (768 dimensions) in the `ArticleNode`.

### 4. Graph Construction (`GraphConstruction`)
*   **Source**: `src/application/pipeline/graph_construction.py`
*   **Function**: Persists the in-memory Domain Model into the Neo4j Graph Database.
*   **Graph Schema**:
    *   `(:Normativa)`: The root node.
    *   `(:Structure)`: Intermediate nodes (Books, Titles).
    *   `(:Article)`: The leaf nodes containing text and embeddings.
    *   **Relationships**: `[:CONTAINS]`, `[:NEXT_VERSION]`.
