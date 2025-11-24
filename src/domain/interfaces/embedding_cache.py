from abc import ABC, abstractmethod
from typing import List, Optional

class EmbeddingCache(ABC):
    """
    Abstract base class for embedding cache.
    """
    
    @abstractmethod
    def get(self, key: str) -> Optional[List[float]]:
        """Retrieve embedding by key (hash)."""
        pass
    
    @abstractmethod
    def set(self, key: str, embedding: List[float]):
        """Store embedding by key (hash)."""
        pass
        
    @abstractmethod
    def save(self):
        """Persist cache to storage."""
        pass
