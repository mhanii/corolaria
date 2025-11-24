from dataclasses import dataclass

@dataclass
class EmbeddingConfig:
    """
    Configuration for embedding model and vector index.
    Ensures that the provider and the indexer use the same settings.
    """
    model_name: str
    dimensions: int
    similarity: str = "cosine" # Options: cosine, euclidean, dot
    task_type: str = "RETRIEVAL_DOCUMENT" # Gemini task type
