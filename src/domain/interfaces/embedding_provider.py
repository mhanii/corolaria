from abc import ABC, abstractmethod
from typing import List

class EmbeddingProvider(ABC):
    """
    Abstract base class for embedding providers.
    """
    
    def __init__(self, model: str, dimensions: int):
        self.model = model
        self.dimensions = dimensions

    @abstractmethod
    def get_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text string.
        """
        pass

    @abstractmethod
    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of text strings.
        """
        pass
