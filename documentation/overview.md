# Coloraria: Legal Agent (Copilot) Architecture

## 1. Vision & Purpose
**Coloraria** is designed to be an advanced **Legal Agent (Copilot)** capable of assisting legal professionals by understanding, retrieving, and reasoning about complex legal frameworks.

Unlike simple keyword search engines, Coloraria builds a **semantic and structural understanding** of the law. It ingests raw legal texts (from the BOE), models them as a **Knowledge Graph**, and enriches them with **Vector Embeddings**. This allows the agent to answer questions like:
*   *"What are the requirements for X under Article Y?"*
*   *"How has this regulation changed since 2020?"*
*   *"Find all articles related to 'environmental liability' in the Civil Code."*

## 2. High-Level Architecture

The system is composed of three main layers:

### A. The Knowledge Layer (Ingestion Pipeline)
*   **Purpose**: To build the "Brain" of the agent.
*   **Mechanism**: A robust pipeline (`Doc2Graph`) that fetches laws, parses their hierarchical structure (Books, Titles, Articles), and persists them into a **Graph Database (Neo4j)**.
*   **Enrichment**: Each article is processed through an **AI Embedding Model (Gemini)** to generate vector representations, enabling semantic search.

### B. The Reasoning Layer (AI & Retrieval)
*   **Purpose**: To understand user queries and fetch relevant context.
*   **Mechanism**:
    *   **Vector Search (Qdrant/Neo4j)**: Finds articles semantically similar to the user's query.
    *   **Graph Traversal**: Navigates the legal hierarchy (e.g., "Get the parent Chapter of this Article") to provide context.
    *   **LLM Integration**: Uses Large Language Models (like Gemini) to synthesize answers based on the retrieved legal context (RAG - Retrieval Augmented Generation).

### C. The Application Layer (Copilot Interface)
*   **Purpose**: The interface for the user.
*   **Mechanism**: (Planned) A chat interface or API where users interact with the agent. The agent maintains conversation history and context.

## 3. Core Technologies
*   **Language**: Python 3.x
*   **Graph Database**: Neo4j (Stores structure: `Law -> Book -> Title -> Article`).
*   **Vector Database**: Neo4j / Qdrant (Stores semantic embeddings).
*   **AI Models**: Google Gemini (`gemini-embedding-001` for embeddings, `gemini-pro` for reasoning).
*   **Data Source**: BOE (Boletín Oficial del Estado) API.

## 4. Directory Structure
*   `src/application/pipeline`: The core ingestion logic.
*   `src/domain`: The business logic and data models (DDD approach).
*   `src/infrastructure`: Adapters for databases and external APIs.
*   `src/ai`: AI model integrations (Embeddings, LLMs).
