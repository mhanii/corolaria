from abc import ABC, abstractmethod
from typing import List, Any, Dict
from src.domain.value_objects.embedding_config import EmbeddingConfig

class VectorIndexer(ABC):
    """
    Abstract base class for vector indexers.
    """
    
    def __init__(self, config: EmbeddingConfig):
        self.config = config

    @abstractmethod
    def create_index(self):
        """
        Create the vector index or collection if it doesn't exist.
        Should use self.config.dimensions and self.config.similarity.
        """
        pass
    
    @abstractmethod
    def drop_index(self):
        """
        Drop the vector index or collection if it exists.
        """
        pass
    
    @abstractmethod
    def upsert(self, items: List[Dict[str, Any]]):
        """
        Upsert vectors into the index.
        
        Args:
            items: List of dictionaries containing at least:
                   - id: str
                   - vector: List[float]
                   - payload: Dict[str, Any] (optional metadata)
        """
        pass
