from typing import List, Dict, Any
from src.domain.interfaces.retrieval_strategy import RetrievalStrategy
from src.domain.value_objects.search_result import SearchResult
from src.domain.interfaces.embedding_provider import EmbeddingProvider
from src.domain.interfaces.graph_adapter import GraphAdapter
from src.utils.logger import step_logger

class VectorSearchStrategy(RetrievalStrategy):
    """
    Retrieval strategy using semantic similarity via vector embeddings.
    Generates embedding for the query and searches for similar articles.
    """
    
    def __init__(self, adapter: GraphAdapter, embedding_provider: EmbeddingProvider):
        """
        Args:
            adapter: Graph adapter for database queries (implements GraphAdapter)
            embedding_provider: Provider to generate query embeddings
        """
        super().__init__(name="Vector Search")
        self.adapter = adapter
        self.embedding_provider = embedding_provider
    
    def search(self, query: str, top_k: int = 10, **kwargs) -> List[SearchResult]:
        """
        Perform semantic vector search.
        
        Args:
            query: Natural language query
            top_k: Number of results to return
            **kwargs: 
                - index_name: Name of vector index (default: "article_embeddings")
                
        Returns:
            List of SearchResult objects ordered by similarity
        """
        step_logger.info(f"[VectorSearchStrategy] Searching for: '{query}' (top_k={top_k})")
        
        # Generate embedding for the query
        query_embedding = self.embedding_provider.get_embedding(query)
        step_logger.info(f"[VectorSearchStrategy] Generated query embedding (dim={len(query_embedding)})")
        
        # Perform vector search
        index_name = kwargs.get("index_name", "article_embeddings")
        raw_results = self.adapter.vector_search(
            query_embedding=query_embedding,
            top_k=top_k,
            index_name=index_name
        )
        
        step_logger.info(f"[VectorSearchStrategy] Found {len(raw_results)} results")
        
        # Transform to SearchResult objects
        search_results = []
        for result in raw_results:

            article_text = self.adapter.get_article_rich_text(result.get("article_id", ""))
            search_result = SearchResult(
                article_id=result.get("article_id", ""),
                article_number=result.get("article_number", ""),
                article_text=article_text,
                normativa_title=result.get("normativa_title", ""),
                normativa_id=result.get("normativa_id", ""),
                score=float(result.get("score", 0.0)),
                strategy_used=self.name,
                context_path=result.get("context_path", []),
                metadata={
                    "has_embedding": result.get("embedding") is not None,
                    "query": query
                }
            )
            search_results.append(search_result)
        

        return search_results
