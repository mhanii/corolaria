from typing import List, Dict
from src.domain.interfaces.retrieval_strategy import RetrievalStrategy
from src.domain.value_objects.search_result import SearchResult
from src.ai.rag.vector_search_strategy import VectorSearchStrategy
from src.ai.rag.keyword_search_strategy import KeywordSearchStrategy
from src.utils.logger import step_logger

class HybridSearchStrategy(RetrievalStrategy):
    """
    Hybrid retrieval strategy that combines vector and keyword search.
    Merges results with configurable weighting.
    """
    
    def __init__(self, vector_strategy: VectorSearchStrategy, 
                 keyword_strategy: KeywordSearchStrategy,
                 vector_weight: float = 0.7):
        """
        Args:
            vector_strategy: Vector search strategy instance
            keyword_strategy: Keyword search strategy instance
            vector_weight: Weight for vector search results (0-1), keyword gets (1-weight)
        """
        super().__init__(name="Hybrid Search")
        self.vector_strategy = vector_strategy
        self.keyword_strategy = keyword_strategy
        self.vector_weight = vector_weight
        self.keyword_weight = 1.0 - vector_weight
        
        step_logger.info(f"[HybridSearchStrategy] Initialized with weights: "
                        f"vector={vector_weight:.2f}, keyword={self.keyword_weight:.2f}")
    
    def search(self, query: str, top_k: int = 10, **kwargs) -> List[SearchResult]:
        """
        Perform hybrid search combining vector and keyword strategies.
        
        Args:
            query: Search query
            top_k: Number of results to return
            **kwargs:
                - vector_weight: Override default vector weight
                - rerank: Whether to re-rank combined results (default: True)
                
        Returns:
            List of SearchResult objects with combined scores
        """
        step_logger.info(f"[HybridSearchStrategy] Performing hybrid search: '{query}'")
        
        # Override weights if provided
        vector_weight = kwargs.get("vector_weight", self.vector_weight)
        keyword_weight = 1.0 - vector_weight
        
        # Perform both searches (request more results for better merging)
        k_multiplier = kwargs.get("k_multiplier", 2)
        fetch_k = min(top_k * k_multiplier, 50)
        
        vector_results = self.vector_strategy.search(query, top_k=fetch_k, **kwargs)
        keyword_results = self.keyword_strategy.search(query, top_k=fetch_k, **kwargs)
        
        step_logger.info(f"[HybridSearchStrategy] Vector: {len(vector_results)}, "
                        f"Keyword: {len(keyword_results)} results")
        
        # Merge and re-score
        merged = self._merge_results(
            vector_results, keyword_results,
            vector_weight, keyword_weight
        )
        
        # Sort by combined score and take top_k
        merged.sort(key=lambda x: x.score, reverse=True)
        final_results = merged[:top_k]
        
        # Update strategy name in results
        for result in final_results:
            result.strategy_used = self.name
            result.metadata["vector_weight"] = vector_weight
            result.metadata["keyword_weight"] = keyword_weight
        
        step_logger.info(f"[HybridSearchStrategy] Returning {len(final_results)} merged results")
        
        return final_results
    
    def _merge_results(self, vector_results: List[SearchResult], 
                      keyword_results: List[SearchResult],
                      vector_weight: float, keyword_weight: float) -> List[SearchResult]:
        """
        Merge results from two strategies, combining scores for duplicates.
        
        Args:
            vector_results: Results from vector search
            keyword_results: Results from keyword search
            vector_weight: Weight for vector scores
            keyword_weight: Weight for keyword scores
            
        Returns:
            Merged list of SearchResult objects with combined scores
        """
        # Create a map of article_id -> SearchResult with combined scores
        result_map: Dict[str, SearchResult] = {}
        
        # Process vector results
        for result in vector_results:
            article_id = result.article_id
            weighted_score = result.score * vector_weight
            
            if article_id not in result_map:
                # Create new result with weighted score
                result_copy = SearchResult(
                    article_id=result.article_id,
                    article_number=result.article_number,
                    article_text=result.article_text,
                    normativa_title=result.normativa_title,
                    normativa_id=result.normativa_id,
                    score=weighted_score,
                    strategy_used=result.strategy_used,
                    context_path=result.context_path,
                    metadata={
                        **result.metadata,
                        "vector_score": result.score,
                        "keyword_score": 0.0
                    }
                )
                result_map[article_id] = result_copy
            else:
                # Add to existing score
                result_map[article_id].score += weighted_score
                result_map[article_id].metadata["vector_score"] = result.score
        
        # Process keyword results
        for result in keyword_results:
            article_id = result.article_id
            weighted_score = result.score * keyword_weight
            
            if article_id not in result_map:
                # Create new result with weighted score
                result_copy = SearchResult(
                    article_id=result.article_id,
                    article_number=result.article_number,
                    article_text=result.article_text,
                    normativa_title=result.normativa_title,
                    normativa_id=result.normativa_id,
                    score=weighted_score,
                    strategy_used=result.strategy_used,
                    context_path=result.context_path,
                    metadata={
                        **result.metadata,
                        "vector_score": 0.0,
                        "keyword_score": result.score
                    }
                )
                result_map[article_id] = result_copy
            else:
                # Add to existing score
                result_map[article_id].score += weighted_score
                result_map[article_id].metadata["keyword_score"] = result.score
        
        return list(result_map.values())
