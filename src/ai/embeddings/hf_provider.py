from typing import List
from src.domain.interfaces.embedding_provider import EmbeddingProvider
# try:
#     from sentence_transformers import SentenceTransformer
# except ImportError:
#     SentenceTransformer = None

class HuggingFaceEmbeddingProvider(EmbeddingProvider):
    """
    Embedding provider using HuggingFace Sentence Transformers (local).
    """
    
    def __init__(self, model: str = "all-MiniLM-L6-v2", dimensions: int = 384):
        super().__init__(model, dimensions)
        # if SentenceTransformer is None:
        #     raise ImportError("sentence_transformers is not installed. Please install it with `pip install sentence-transformers`.")
        self.client = None

    def get_embedding(self, text: str) -> List[float]:
        if self.client is None:
            raise ValueError("Client not initialized. Please call the 'init' method first.")
        embedding = self.client.encode(text)
        return embedding.tolist()

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        embeddings = self.client.encode(texts)
        return embeddings.tolist()
