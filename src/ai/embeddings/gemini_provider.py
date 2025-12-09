from typing import List
import os
import time
from src.domain.interfaces.embedding_provider import EmbeddingProvider
from src.utils.logger import step_logger, output_logger

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None

# Retry configuration
MAX_RETRIES = 3
BASE_DELAY = 1.0  # seconds


def _retry_with_backoff(func):
    """Decorator for exponential backoff retry on transient errors."""
    def wrapper(*args, **kwargs):
        last_exception = None
        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                error_str = str(e).lower()
                # Check for transient errors worth retrying
                is_transient = any(x in error_str for x in [
                    '429', 'rate limit', 'quota', 'resource exhausted',
                    '500', '502', '503', '504', 'server error',
                    'timeout', 'connection'
                ])
                if not is_transient or attempt == MAX_RETRIES - 1:
                    raise
                delay = BASE_DELAY * (2 ** attempt)
                step_logger.warning(f"Transient error, retrying in {delay}s (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                time.sleep(delay)
        raise last_exception
    return wrapper


class GeminiEmbeddingProvider(EmbeddingProvider):
    """
    Embedding provider using Google Gemini API via google-genai library.
    Includes exponential backoff retry for transient errors.
    """
    def __init__(self, model: str = "models/gemini-embedding-001", dimensions: int = 768, task_type: str = "RETRIEVAL_DOCUMENT"):
        super().__init__(model, dimensions)
        self.task_type = task_type
        if genai is None:
            step_logger.error("google-genai library not found.")
            raise ImportError("google-genai is not installed.")
            
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            step_logger.warning("GOOGLE_API_KEY not set. Gemini provider might fail.")
            
        self.client = genai.Client(api_key=api_key)
        step_logger.info(f"Initialized GeminiEmbeddingProvider with model={model}, dimensions={dimensions}, task_type={task_type}")

    @_retry_with_backoff
    def get_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        Retries on transient errors with exponential backoff.
        """
        step_logger.info(f"Generating embedding for single text (length={len(text)})")
        result = self.client.models.embed_content(
            model=self.model,
            contents=text,
            config=types.EmbedContentConfig(
                task_type=self.task_type,
                output_dimensionality=self.dimensions
            )
        )
        embedding = result.embeddings[0].values
        output_logger.info(f"--- [GeminiProvider] Generated Embedding ---\nSize: {len(embedding)}\nPreview: {embedding[:5]}...\n")
        return embedding


    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts.
        Gemini supports batching, but we should respect limits (e.g. 100).
        Each batch is retried with exponential backoff on transient errors.
        """
        BATCH_SIZE = 100
        all_embeddings = []
        step_logger.info(f"Generating embeddings for {len(texts)} texts in batches of {BATCH_SIZE}")
        
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            step_logger.info(f"Processing batch {i//BATCH_SIZE + 1} (size={len(batch)})")
            batch_embeddings = self._embed_batch(batch)
            all_embeddings.extend(batch_embeddings)
                
        return all_embeddings

    @_retry_with_backoff
    def _embed_batch(self, batch: List[str]) -> List[List[float]]:
        """Embed a single batch with retry support."""
        result = self.client.models.embed_content(
            model=self.model,
            contents=batch,
            config=types.EmbedContentConfig(
                task_type=self.task_type,
                output_dimensionality=self.dimensions
            )
        )
        batch_embeddings = [e.values for e in result.embeddings]
        output_logger.info(f"--- [GeminiProvider] Generated Batch Embeddings ---\nCount: {len(batch_embeddings)}\nFirst Embedding Preview: {batch_embeddings[0][:5]}...\n")
        return batch_embeddings

