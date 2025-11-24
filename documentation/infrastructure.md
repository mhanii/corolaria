# Infrastructure Layer

## Overview
The Infrastructure layer handles all external communications, database persistence, and technical plumbing. It implements the interfaces defined in the Domain layer, ensuring the core logic remains decoupled from specific tools.

**Location**: `src/infrastructure/`

## 1. Graph Database (Neo4j)
*   **Location**: `src/infrastructure/graphdb/`
*   **Components**:
    *   `Neo4jConnection`: Manages the driver connection and sessions.
    *   `Neo4jAdapter`: A wrapper around the driver to execute Cypher queries. It abstracts the raw driver calls.
*   **Configuration**: Requires `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` in `.env`.

## 2. HTTP Client (BOE)
*   **Location**: `src/infrastructure/http/`
*   **Component**: `BOEHTTPClient`.
*   **Library**: `httpx` (for async support).
*   **Role**: Fetches legal documents from the external BOE API. Handles retries and error checking.

## 3. Logging
*   **Location**: `src/utils/logger.py`
*   **Strategy**:
    *   `step_logger`: Logs high-level pipeline progress (INFO/ERROR).
    *   `output_logger`: Logs detailed data inspection (e.g., content of articles being processed).
