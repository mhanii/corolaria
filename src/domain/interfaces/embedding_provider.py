from abc import ABC, abstractmethod
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.interfaces.embedding_cache import EmbeddingCache


class EmbeddingProvider(ABC):
    """
    Abstract base class for embedding providers with built-in caching support.
    
    Subclasses implement _generate_embedding() and _generate_embeddings() for
    actual embedding generation. The base class handles caching automatically.
    """
    
    def __init__(self, model: str, dimensions: int, cache: Optional["EmbeddingCache"] = None):
        self.model = model
        self.dimensions = dimensions
        self._cache = cache

    def get_embedding(self, text: str) -> List[float]:
        """
        Get embedding for text, using cache if available.
        """
        # Check cache first
        if self._cache:
            cached = self._cache.get(text)
            if cached is not None:
                return cached
        
        # Generate embedding
        embedding = self._generate_embedding(text)
        
        # Store in cache
        if self._cache:
            self._cache.set(text, embedding)
            self._cache.save()
        
        return embedding

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Get embeddings for multiple texts, using cache where available.
        """
        if not self._cache:
            return self._generate_embeddings(texts)
        
        results: List[Optional[List[float]]] = [None] * len(texts)
        texts_to_generate: List[str] = []
        indices_to_generate: List[int] = []
        
        # Check cache for each text
        for i, text in enumerate(texts):
            cached = self._cache.get(text)
            if cached is not None:
                results[i] = cached
            else:
                texts_to_generate.append(text)
                indices_to_generate.append(i)
        
        # Generate missing embeddings
        if texts_to_generate:
            generated = self._generate_embeddings(texts_to_generate)
            for idx, embedding in zip(indices_to_generate, generated):
                results[idx] = embedding
                self._cache.set(texts_to_generate[indices_to_generate.index(idx)], embedding)
            self._cache.save()
        
        return results  # type: ignore

    @abstractmethod
    def _generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text string.
        Subclasses must implement this.
        """
        pass

    @abstractmethod
    def _generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.
        Subclasses must implement this.
        """
        pass
