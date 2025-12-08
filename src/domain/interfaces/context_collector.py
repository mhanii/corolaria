"""
Context Collector Interface.

Abstract base class for unified context-gathering strategies.
Supports pluggable implementations: RAG, graph traversal, hybrid, voyager agents, etc.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class ContextResult:
    """
    Unified result from any context collection strategy.
    
    Provides a common format for all context collectors, making them
    interchangeable in the workflow graph.
    
    Attributes:
        chunks: List of retrieved context chunks (article data, graph nodes, etc.)
        strategy_name: Name of the strategy that produced these results
        metadata: Additional strategy-specific metadata (e.g., scores, query info)
    """
    chunks: List[Dict[str, Any]]
    strategy_name: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __len__(self) -> int:
        """Return the number of chunks collected."""
        return len(self.chunks)
    
    def is_empty(self) -> bool:
        """Check if no context was collected."""
        return len(self.chunks) == 0


class ContextCollector(ABC):
    """
    Abstract base class for context collection strategies.
    
    This is the unified interface for all context-gathering approaches.
    Implementations can include:
    
    - RAGContextCollector: Classic vector search + embedding
    - GraphContextCollector: Graph-based traversal and exploration
    - HybridContextCollector: Combined vector + graph strategies
    - VoyagerContextCollector: Tool-using agent that gathers context
    - QueryRewriteCollector: LLM-powered query reformulation + retrieval
    
    Each collector takes a query and returns a ContextResult with the
    gathered context chunks.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """
        Human-readable name of this context collector.
        
        Returns:
            String identifier for this collector (e.g., "RAGContextCollector")
        """
        pass
    
    @abstractmethod
    def collect(
        self, 
        query: str, 
        top_k: int = 10,
        **kwargs
    ) -> ContextResult:
        """
        Collect context for the given query.
        
        Args:
            query: The user's query or question
            top_k: Maximum number of context chunks to retrieve
            **kwargs: Strategy-specific parameters (e.g., index_name, similarity_threshold)
            
        Returns:
            ContextResult containing the collected chunks and metadata
        """
        pass
    
    def __str__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name})"
    
    def __repr__(self) -> str:
        return self.__str__()
