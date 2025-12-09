# Coloraria System Documentation

Welcome to the technical documentation for **Coloraria**, an advanced RAG-based legal AI assistant.

## Service Documentation

The documentation is organized by service:

*   **[Ingestion Service](services/ingestion.md)**: How legal documents are fetched, processed, and stored in the Graph.
*   **[Retrieval Service](services/retrieval.md)**: Search strategies (Vector, Hybrid, Graph) and RAG enrichment logic.
*   **[Chat Service](services/chat.md)**: Context management, conversation history, and citation unification (LangGraph).
*   **[Benchmark Service](services/benchmark.md)**: Evaluation framework for running exams and testing performance.
*   **[API Service](services/api.md)**: REST API endpoints reference.

## Domain Documentation

*   **[Graph Schema](graph_schema.md)**: Detailed reference of Node types (`Normativa`, `articulo`), Relationships (`PART_OF`, `NEXT_VERSION`, `REFERS_TO`), and Graph structure.

## Development & Planning

*   **[Weekly Improvement Plan (TODO)](TODO.md)**: "The Edge" - Roadmap for upcoming advanced features.
