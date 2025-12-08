"""
Context Collectors - Pluggable context gathering strategies.

This module provides interchangeable context collection strategies for the agent graph.
Each collector implements the ContextCollector interface and can be swapped at runtime.

Available Collectors:
    - RAGCollector: Classic vector search using embeddings
    - QRAGCollector: Query-optimized RAG with LLM-generated search queries
"""
from src.ai.context_collectors.rag_context_collector import RAGCollector
from src.ai.context_collectors.qrag_collector import QRAGCollector

__all__ = ["RAGCollector", "QRAGCollector"]
