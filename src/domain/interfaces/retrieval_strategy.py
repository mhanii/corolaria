from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from src.domain.value_objects.search_result import SearchResult

class RetrievalStrategy(ABC):
    """
    Abstract base class for retrieval strategies.
    Each strategy implements a different approach to finding relevant articles.
    """
    
    def __init__(self, name: str):
        """
        Args:
            name: Human-readable name for this strategy
        """
        self.name = name
    
    @abstractmethod
    def search(self, query: str, top_k: int = 10, **kwargs) -> List[SearchResult]:
        """
        Perform a search using this strategy.
        
        Args:
            query: Search query (can be text, keywords, or structured query depending on strategy)
            top_k: Maximum number of results to return
            **kwargs: Strategy-specific parameters
            
        Returns:
            List of SearchResult objects, ordered by relevance
        """
        pass
    
    def get_name(self) -> str:
        """Get the name of this strategy."""
        return self.name
    
    def __str__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name})"
