from typing import List
import os
from src.domain.interfaces.embedding_provider import EmbeddingProvider
from src.utils.logger import step_logger, output_logger

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None

class GeminiEmbeddingProvider(EmbeddingProvider):
    """
    Embedding provider using Google Gemini API via google-genai library.
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

    def get_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        """
        step_logger.info(f"Generating embedding for single text (length={len(text)})")
        try:
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
        except Exception as e:
            step_logger.error(f"Error generating Gemini embedding: {e}")
            raise

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts.
        Gemini supports batching, but we should respect limits (e.g. 100).
        """
        BATCH_SIZE = 100
        all_embeddings = []
        step_logger.info(f"Generating embeddings for {len(texts)} texts in batches of {BATCH_SIZE}")
        
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            step_logger.info(f"Processing batch {i//BATCH_SIZE + 1} (size={len(batch)})")
            try:
                result = self.client.models.embed_content(
                    model=self.model,
                    contents=batch,
                    config=types.EmbedContentConfig(
                        task_type=self.task_type,
                        output_dimensionality=self.dimensions
                    )
                )
                # Extract values from each Embedding object
                batch_embeddings = [e.values for e in result.embeddings]
                all_embeddings.extend(batch_embeddings)
                
                output_logger.info(f"--- [GeminiProvider] Generated Batch Embeddings ---\nCount: {len(batch_embeddings)}\nFirst Embedding Preview: {batch_embeddings[0][:5]}...\n")
                
            except Exception as e:
                step_logger.error(f"Error generating Gemini batch embeddings: {e}")
                raise
                
        return all_embeddings
