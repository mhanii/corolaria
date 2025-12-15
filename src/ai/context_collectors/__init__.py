"""
Context Collectors - Pluggable context gathering strategies.

This module provides interchangeable context collection strategies for the agent graph.
Each collector implements the ContextCollector interface and can be swapped at runtime.

Available Collectors:
    - RAGCollector: Classic vector search using embeddings
    - QRAGCollector: Query-optimized RAG with LLM-generated search queries
    - AgentCollector: LLM agent with tools for dynamic graph exploration
"""
from src.ai.context_collectors.rag_context_collector import RAGCollector
from src.ai.context_collectors.qrag_collector import QRAGCollector
from src.ai.context_collectors.agent_collector import AgentCollector

__all__ = ["RAGCollector", "QRAGCollector", "AgentCollector"]

