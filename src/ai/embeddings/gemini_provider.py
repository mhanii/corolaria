"""
Gemini Embedding Provider.

Supports both real API calls and simulation mode for stress testing.
Simulation mode generates fake embeddings with realistic latency to stress-test 
the pipeline architecture without incurring API costs.
"""
from typing import List
import os
import time
import random
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
    
    Supports simulation mode for stress testing without API costs.
    Includes exponential backoff retry for transient errors.
    """
    
    def __init__(
        self, 
        model: str = "models/gemini-embedding-001", 
        dimensions: int = 768, 
        task_type: str = "RETRIEVAL_DOCUMENT",
        simulate: bool = False
    ):
        super().__init__(model, dimensions)
        self.task_type = task_type
        self.simulate = simulate
        self.client = None
        
        if simulate:
            step_logger.info(
                f"Initialized GeminiEmbeddingProvider in SIMULATION mode "
                f"(model={model}, dimensions={dimensions})"
            )
        else:
            if genai is None:
                step_logger.error("google-genai library not found.")
                raise ImportError("google-genai is not installed.")
                
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                step_logger.warning("GOOGLE_API_KEY not set. Gemini provider might fail.")
                
            self.client = genai.Client(api_key=api_key)
            step_logger.info(
                f"Initialized GeminiEmbeddingProvider with model={model}, "
                f"dimensions={dimensions}, task_type={task_type}"
            )

    def _simulate_embedding(self) -> List[float]:
        """Generate a random embedding vector for simulation."""
        return [random.uniform(-1.0, 1.0) for _ in range(self.dimensions)]
    
    def _simulate_batch(self, batch_size: int) -> List[List[float]]:
        """Generate batch of random embeddings with realistic latency."""
        # Simulate realistic API latency: ~3s per batch of 100 texts
        time.sleep(3.0)
        return [self._simulate_embedding() for _ in range(batch_size)]

    @_retry_with_backoff
    def get_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        Retries on transient errors with exponential backoff.
        """
        if self.simulate:
            time.sleep(random.uniform(0.05, 0.15))
            return self._simulate_embedding()
        
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
        total_batches = (len(texts) + BATCH_SIZE - 1) // BATCH_SIZE
        mode_str = "SIM" if self.simulate else "API"
        step_logger.info(f"[{mode_str}] Generating {len(texts)} embeddings in {total_batches} batches...")
        
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            
            if self.simulate:
                step_logger.info(f"[SIM] Batch {batch_num}/{total_batches} ({len(batch)} texts) - waiting 3s...")
                batch_embeddings = self._simulate_batch(len(batch))
            else:
                step_logger.info(f"[API] Batch {batch_num}/{total_batches} ({len(batch)} texts)")
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
