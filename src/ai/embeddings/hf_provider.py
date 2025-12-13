from typing import List, Optional, TYPE_CHECKING
from src.domain.interfaces.embedding_provider import EmbeddingProvider

if TYPE_CHECKING:
    from src.domain.interfaces.embedding_cache import EmbeddingCache

# try:
#     from sentence_transformers import SentenceTransformer
# except ImportError:
#     SentenceTransformer = None

class HuggingFaceEmbeddingProvider(EmbeddingProvider):
    """
    Embedding provider using HuggingFace Sentence Transformers (local).
    """
    
    def __init__(
        self, 
        model: str = "all-MiniLM-L6-v2", 
        dimensions: int = 384,
        cache: Optional["EmbeddingCache"] = None
    ):
        super().__init__(model, dimensions, cache)
        # if SentenceTransformer is None:
        #     raise ImportError("sentence_transformers is not installed. Please install it with `pip install sentence-transformers`.")
        self.client = None

    def _generate_embedding(self, text: str) -> List[float]:
        if self.client is None:
            raise ValueError("Client not initialized. Please call the 'init' method first.")
        embedding = self.client.encode(text)
        return embedding.tolist()

    def _generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        embeddings = self.client.encode(texts)
        return embeddings.tolist()

