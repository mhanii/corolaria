from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

@dataclass
class SearchResult:
    """
    Value object representing a search result from any retrieval strategy.
    """
    article_id: str
    article_number: str
    article_text: str
    normativa_title: str
    normativa_id: str
    score: float
    strategy_used: str
    context_path: List[Dict[str, str]]  # e.g., [{"type": "Título", "name": "I"}, ...]
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_context_path_string(self) -> str:
        """
        Format context path as readable string.
        Returns: "Libro I > Título II > Capítulo III"
        """
        if not self.context_path:
            return "General"
        
        # Reverse to get root-to-leaf order and skip ROOT if present
        path_items = []
        for item in reversed(self.context_path):
            if item.get("type") == "ROOT":
                continue
            item_type = item.get("type", "").capitalize()
            item_name = item.get("name", "")
            if item_type and item_name:
                path_items.append(f"{item_type} {item_name}")
        
        return " > ".join(path_items) if path_items else "General"
    
    def get_preview(self, max_length: int = 200) -> str:
        """
        Get a preview of the article text.
        """
        if not self.article_text:
            return ""
        
        if len(self.article_text) <= max_length:
            return self.article_text
        
        return self.article_text[:max_length] + "..."
    
    def __str__(self) -> str:
        """String representation for debugging."""
        return (f"SearchResult(article={self.article_number}, "
                f"score={self.score:.3f}, strategy={self.strategy_used})")


@dataclass
class BenchmarkResult:
    """
    Value object for storing benchmark results when comparing strategies.
    """
    strategy_name: str
    query: str
    num_results: int
    execution_time_ms: float
    results: List[SearchResult]
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_avg_score(self) -> float:
        """Calculate average score of results."""
        if not self.results:
            return 0.0
        return sum(r.score for r in self.results) / len(self.results)
    
    def get_top_k_ids(self, k: int = 5) -> List[str]:
        """Get IDs of top-k results."""
        return [r.article_id for r in self.results[:k]]
