from typing import Optional, TYPE_CHECKING
from src.domain.interfaces.embedding_provider import EmbeddingProvider
from src.ai.embeddings.hf_provider import HuggingFaceEmbeddingProvider
from src.ai.embeddings.gemini_provider import GeminiEmbeddingProvider

if TYPE_CHECKING:
    from src.domain.interfaces.embedding_cache import EmbeddingCache


class EmbeddingFactory:
    @staticmethod
    def create(
        provider: str, 
        model: Optional[str] = None, 
        dimensions: Optional[int] = None, 
        cache: Optional["EmbeddingCache"] = None,
        **kwargs
    ) -> EmbeddingProvider:
        if provider.lower() == "huggingface":
            # Defaults for HF
            model = model or "all-MiniLM-L6-v2"
            dimensions = dimensions or 384
            return HuggingFaceEmbeddingProvider(model=model, dimensions=dimensions, cache=cache)
        
        elif provider.lower() == "gemini":
            return GeminiEmbeddingProvider(
                model=model or "models/gemini-embedding-001", 
                dimensions=dimensions or 768,
                task_type=kwargs.get("task_type", "RETRIEVAL_DOCUMENT"),
                simulate=kwargs.get("simulate", False),
                cache=cache
            )
        
        else:
            raise ValueError(f"Unknown embedding provider: {provider}")



