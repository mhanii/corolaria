from typing import List
from src.domain.interfaces.retrieval_strategy import RetrievalStrategy
from src.domain.value_objects.search_result import SearchResult
from src.infrastructure.graphdb.adapter import Neo4jAdapter
from src.utils.logger import step_logger

class KeywordSearchStrategy(RetrievalStrategy):
    """
    Retrieval strategy using keyword/text matching.
    Searches for exact or fuzzy matches in article text and titles.
    """
    
    def __init__(self, adapter: Neo4jAdapter):
        """
        Args:
            adapter: Neo4j adapter for database queries
        """
        super().__init__(name="Keyword Search")
        self.adapter = adapter
    
    def search(self, query: str, top_k: int = 10, **kwargs) -> List[SearchResult]:
        """
        Perform keyword-based search.
        
        Args:
            query: Keywords to search for
            top_k: Number of results to return
            **kwargs:
                - case_sensitive: Whether to use case-sensitive matching (default: False)
                
        Returns:
            List of SearchResult objects ordered by relevance
        """
        step_logger.info(f"[KeywordSearchStrategy] Searching for keywords: '{query}' (top_k={top_k})")
        
        # Perform keyword search
        raw_results = self.adapter.keyword_search(
            keywords=query,
            top_k=top_k
        )
        
        step_logger.info(f"[KeywordSearchStrategy] Found {len(raw_results)} results")
        
        # Transform to SearchResult objects
        # Since keyword search doesn't have a natural score, we'll assign based on position
        search_results = []
        for idx, result in enumerate(raw_results):
            # Simple scoring: 1.0 for first result, decreasing linearly
            score = 1.0 - (idx / max(len(raw_results), 1))
            
            search_result = SearchResult(
                article_id=result.get("article_id", ""),
                article_number=result.get("article_number", ""),
                article_text=result.get("article_text", ""),
                normativa_title=result.get("normativa_title", ""),
                normativa_id=result.get("normativa_id", ""),
                score=score,
                strategy_used=self.name,
                context_path=result.get("context_path", []),
                metadata={
                    "position": idx + 1,
                    "query": query
                }
            )
            search_results.append(search_result)
        
        return search_results
