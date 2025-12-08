"""
RAG Context Collector.

Default context collector using semantic vector search (Retrieval-Augmented Generation).
Wraps the existing Neo4j vector search and embedding provider.
"""
from typing import List, Dict, Any

from src.domain.interfaces.context_collector import ContextCollector, ContextResult
from src.domain.interfaces.embedding_provider import EmbeddingProvider
from src.infrastructure.graphdb.adapter import Neo4jAdapter
from src.utils.logger import step_logger

# Import tracer for Phoenix observability
try:
    from opentelemetry import trace
    _tracer = trace.get_tracer("rag_collector")
except ImportError:
    _tracer = None


class RAGCollector(ContextCollector):
    """
    Context collector using semantic vector search (RAG).
    
    This is the default implementation that replicates the behavior of the
    original `retrieve_node`. It generates an embedding for the query and
    performs vector similarity search in Neo4j.
    
    Attributes:
        neo4j_adapter: Neo4j adapter for vector search
        embedding_provider: Provider to generate query embeddings
        index_name: Name of the vector index to search
    """
    
    def __init__(
        self, 
        neo4j_adapter: Neo4jAdapter,
        embedding_provider: EmbeddingProvider,
        index_name: str = "article_embeddings"
    ):
        """
        Initialize the RAG context collector.
        
        Args:
            neo4j_adapter: Neo4j adapter for database queries
            embedding_provider: Provider to generate query embeddings
            index_name: Name of the vector index (default: "article_embeddings")
        """
        self._neo4j_adapter = neo4j_adapter
        self._embedding_provider = embedding_provider
        self._index_name = index_name
        
        step_logger.info(f"[RAGCollector] Initialized with index '{index_name}'")
    
    @property
    def name(self) -> str:
        """Human-readable name of this collector."""
        return "RAGCollector"
    
    def collect(
        self, 
        query: str, 
        top_k: int = 10,
        **kwargs
    ) -> ContextResult:
        """
        Collect context using vector similarity search.
        
        Args:
            query: The user's query
            top_k: Maximum number of chunks to retrieve
            **kwargs:
                - index_name: Override the default index name
                
        Returns:
            ContextResult with retrieved chunks and metadata
        """
        # Start tracing span
        span_context = _tracer.start_as_current_span("rag_collect") if _tracer else None
        
        try:
            if span_context:
                span = span_context.__enter__()
                span.set_attribute("collector.name", self.name)
                span.set_attribute("collector.query", query[:100])
                span.set_attribute("collector.top_k", top_k)
            
            # Allow index_name override via kwargs
            index_name = kwargs.get("index_name", self._index_name)
            
            step_logger.info(f"[RAGCollector] Generating embedding for query...")
            
            # Trace embedding generation
            if _tracer:
                with _tracer.start_as_current_span("rag_generate_embedding") as emb_span:
                    emb_span.set_attribute("input.query", query[:100])
                    query_embedding = self._embedding_provider.get_embedding(query)
                    emb_span.set_attribute("output.dimensions", len(query_embedding))
            else:
                query_embedding = self._embedding_provider.get_embedding(query)
            
            step_logger.info(f"[RAGCollector] Searching vector index (top_k={top_k})...")
            
            # Trace vector search
            if _tracer:
                with _tracer.start_as_current_span("rag_vector_search") as search_span:
                    search_span.set_attribute("search.index_name", index_name)
                    search_span.set_attribute("search.top_k", top_k)
                    chunks = self._neo4j_adapter.vector_search(
                        query_embedding=query_embedding,
                        top_k=top_k,
                        index_name=index_name
                    )
                    search_span.set_attribute("search.results_count", len(chunks))
            else:
                chunks = self._neo4j_adapter.vector_search(
                    query_embedding=query_embedding,
                    top_k=top_k,
                    index_name=index_name
                )
            
            step_logger.info(f"[RAGCollector] Retrieved {len(chunks)} chunks")
            
            if span_context:
                span.set_attribute("output.chunks_count", len(chunks))
            
            return ContextResult(
                chunks=chunks,
                strategy_name=self.name,
                metadata={
                    "index_name": index_name,
                    "top_k": top_k,
                    "embedding_dim": len(query_embedding)
                }
            )
        finally:
            if span_context:
                span_context.__exit__(None, None, None)
