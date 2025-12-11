from typing import List
from src.domain.interfaces.retrieval_strategy import RetrievalStrategy
from src.domain.value_objects.search_result import SearchResult
from src.domain.interfaces.graph_adapter import GraphAdapter
from src.utils.logger import step_logger

class GraphTraversalStrategy(RetrievalStrategy):
    """
    Retrieval strategy using graph structure navigation.
    Supports querying by structure (Title, Chapter), subject matter, and version history.
    """
    
    def __init__(self, adapter: GraphAdapter):
        """
        Args:
            adapter: Graph adapter for database queries (implements GraphAdapter)
        """
        super().__init__(name="Graph Traversal")
        self.adapter = adapter
    
    def search(self, query: str, top_k: int = 10, **kwargs) -> List[SearchResult]:
        """
        Perform graph traversal search.
        
        Args:
            query: Structure ID or search parameters
            top_k: Maximum number of results
            **kwargs:
                - mode: Type of traversal ("structure", "versions", "subject")
                - structure_type: For structure mode (Título, Capítulo, Libro)
                - article_id: For versions mode
                - materia_id: For subject mode
                
        Returns:
            List of SearchResult objects from graph traversal
        """
        mode = kwargs.get("mode", "structure")
        
        step_logger.info(f"[GraphTraversalStrategy] Mode: {mode}, Query: '{query}'")
        
        if mode == "structure":
            return self._search_by_structure(query, top_k, kwargs)
        elif mode == "versions":
            return self._search_versions(query, top_k)
        elif mode == "subject":
            return self._search_by_subject(query, top_k)
        else:
            step_logger.warning(f"[GraphTraversalStrategy] Unknown mode: {mode}")
            return []
    
    def _search_by_structure(self, structure_id: str, top_k: int, kwargs) -> List[SearchResult]:
        """Search all articles in a structural element."""
        structure_type = kwargs.get("structure_type", "Título")
        
        raw_results = self.adapter.get_articles_by_structure(
            structure_id=structure_id,
            structure_type=structure_type
        )
        
        step_logger.info(f"[GraphTraversalStrategy] Found {len(raw_results)} articles in {structure_type}")
        
        return self._transform_results(raw_results, "structure_query")[:top_k]
    
    def _search_versions(self, article_id: str, top_k: int) -> List[SearchResult]:
        """Search all versions of an article."""
        raw_results = self.adapter.get_article_versions(article_id=article_id)
        
        step_logger.info(f"[GraphTraversalStrategy] Found {len(raw_results)} versions")
        
        search_results = []
        for idx, result in enumerate(raw_results):
            # Score based on chronological order (newer = higher score)
            score = (idx + 1) / max(len(raw_results), 1)
            
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
                    "validity_start": result.get("validity_start"),
                    "validity_end": result.get("validity_end"),
                    "version_order": idx + 1,
                    "mode": "versions"
                }
            )
            search_results.append(search_result)
        
        return search_results[:top_k]
    
    def _search_by_subject(self, materia_id: str, top_k: int) -> List[SearchResult]:
        """Search articles by subject matter."""
        raw_results = self.adapter.get_articles_by_subject(materia_id=materia_id)
        
        step_logger.info(f"[GraphTraversalStrategy] Found {len(raw_results)} articles on subject")
        
        return self._transform_results(raw_results, "subject_query")[:top_k]
    
    def _transform_results(self, raw_results: List[dict], mode: str) -> List[SearchResult]:
        """Transform raw database results to SearchResult objects."""
        search_results = []
        
        for idx, result in enumerate(raw_results):
            # Simple position-based scoring
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
                    "mode": mode
                }
            )
            search_results.append(search_result)
        
        return search_results
