"""
RAG Context Collector.

Default context collector using semantic vector search (Retrieval-Augmented Generation).
Wraps the existing Neo4j vector search and embedding provider.
"""
from typing import List, Dict, Any

from src.domain.interfaces.context_collector import ContextCollector, ContextResult
from src.domain.interfaces.embedding_provider import EmbeddingProvider
from src.domain.interfaces.graph_adapter import GraphAdapter
from src.ai.context_collectors.chunk_enricher import ChunkEnricher
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
        neo4j_adapter: GraphAdapter,
        embedding_provider: EmbeddingProvider,
        index_name: str = "article_embeddings"
    ):
        """
        Initialize the RAG context collector.
        
        Args:
            neo4j_adapter: Graph adapter for database queries (implements GraphAdapter)
            embedding_provider: Provider to generate query embeddings
            index_name: Name of the vector index (default: "article_embeddings")
        """
        self._neo4j_adapter = neo4j_adapter
        self._embedding_provider = embedding_provider
        self._index_name = index_name
        self._enricher = ChunkEnricher(neo4j_adapter)
        
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
        # Allow overrides via kwargs
        index_name = kwargs.get("index_name", self._index_name)
        max_refs = kwargs.get("max_refs", ChunkEnricher.DEFAULT_MAX_REFS)
        self._enricher.max_refs = max_refs
        
        step_logger.info(f"[RAGCollector] Generating embedding for query...")
        
        # Use proper context manager for tracing
        if _tracer:
            with _tracer.start_as_current_span("RAGCollector.collect") as span:
                # Record input attributes
                span.set_attribute("collector.name", self.name)
                span.set_attribute("input.query", query)
                span.set_attribute("input.top_k", top_k)
                span.set_attribute("input.index_name", index_name)
                
                # Generate embedding
                query_embedding = self._embedding_provider.get_embedding(query)
                span.set_attribute("embedding.dimensions", len(query_embedding))
                
                step_logger.info(f"[RAGCollector] Searching vector index (top_k={top_k})...")
                
                # Perform vector search
                chunks = self._neo4j_adapter.vector_search(
                    query_embedding=query_embedding,
                    top_k=top_k,
                    index_name=index_name
                )
                
                # Enrich chunks with validity checking and reference expansion
                chunks = self._enricher.enrich_chunks(chunks)
                
                # Record output attributes
                span.set_attribute("output.chunks_count", len(chunks))
                
                # Log full chunk details for each retrieved chunk
                for i, chunk in enumerate(chunks):
                    span.set_attribute(f"output.chunk_{i}.article_number", chunk.get('article_number', 'N/A'))
                    span.set_attribute(f"output.chunk_{i}.normativa_title", chunk.get('normativa_title', 'N/A'))
                    span.set_attribute(f"output.chunk_{i}.score", chunk.get('score', 0))
                    span.set_attribute(f"output.chunk_{i}.text", chunk.get('text', ''))
                
                step_logger.info(f"[RAGCollector] Retrieved {len(chunks)} chunks")
                
                return ContextResult(
                    chunks=chunks,
                    strategy_name=self.name,
                    metadata={
                        "index_name": index_name,
                        "top_k": top_k,
                        "embedding_dim": len(query_embedding)
                    }
                )
        else:
            # No tracing - execute directly
            query_embedding = self._embedding_provider.get_embedding(query)
            
            step_logger.info(f"[RAGCollector] Searching vector index (top_k={top_k})...")
            
            chunks = self._neo4j_adapter.vector_search(
                query_embedding=query_embedding,
                top_k=top_k,
                index_name=index_name
            )
            
            # Enrich chunks with validity checking and reference expansion
            chunks = self._enricher.enrich_chunks(chunks)
            
            step_logger.info(f"[RAGCollector] Retrieved {len(chunks)} chunks")
            
            return ContextResult(
                chunks=chunks,
                strategy_name=self.name,
                metadata={
                    "index_name": index_name,
                    "top_k": top_k,
                    "embedding_dim": len(query_embedding)
                }
            )

