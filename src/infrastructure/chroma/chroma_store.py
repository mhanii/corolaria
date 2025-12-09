"""
ChromaDB store for system classification embeddings.
Used for query classification (e.g., detecting clarification phrases).
"""
import os
import json
from typing import List, Dict, Any, Optional
from pathlib import Path

import chromadb
from chromadb.config import Settings

from src.utils.logger import step_logger


# Default clarification phrases to seed
DEFAULT_CLARIFICATION_PHRASES = [
    # Confirmations / doubt
    "¿estás seguro?",
    "¿estas seguro?",
    "¿seguro?",
    "seguro",
    "¿de verdad?",
    "de verdad",
    "¿en serio?",
    "en serio",
    
    # Elaboration requests
    "explícame más",
    "explicame más",
    "explícame",
    "explica más",
    "dame más detalles",
    "más detalles",
    "¿puedes explicar?",
    "puedes explicar",
    "¿podrías explicar?",
    
    # Clarification
    "¿qué quieres decir?",
    "que quieres decir",
    "¿a qué te refieres?",
    "a que te refieres",
    "no entiendo",
    "no lo entiendo",
    "no comprendo",
    
    # Why/how
    "¿por qué?",
    "por qué",
    "¿cómo?",
    "cómo",
    "¿cómo es eso?",
    
    # Examples
    "dame un ejemplo",
    "un ejemplo",
    "ejemplo por favor",
    "¿puedes dar un ejemplo?",
    
    # Repetition
    "repite",
    "repítelo",
    "otra vez",
    "¿puedes repetir?",
    
    # Simple affirmations that might follow up
    "ok",
    "vale",
    "entiendo",
    "ya veo",
    "ah",
    "ajá",
    "hmm",
]


class ClassificationEmbeddingCache:
    """
    JSON file-based cache for classification embeddings.
    Similar to the article embeddings cache but for classification phrases.
    """
    
    def __init__(self, cache_path: str = "data/classification_embeddings_cache.json"):
        self.cache_path = cache_path
        self.cache: Dict[str, List[float]] = {}
        self._load()
    
    def _load(self):
        """Load cache from file if exists."""
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, 'r', encoding='utf-8') as f:
                    self.cache = json.load(f)
                step_logger.info(f"[ClassificationCache] Loaded {len(self.cache)} cached embeddings")
            except Exception as e:
                step_logger.warning(f"[ClassificationCache] Failed to load: {e}")
                self.cache = {}
        else:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.cache_path) if os.path.dirname(self.cache_path) else ".", exist_ok=True)
            self.cache = {}
    
    def get(self, phrase: str) -> Optional[List[float]]:
        """Get cached embedding for phrase."""
        return self.cache.get(phrase)
    
    def set(self, phrase: str, embedding: List[float]):
        """Cache an embedding."""
        self.cache[phrase] = embedding
    
    def save(self):
        """Persist cache to disk."""
        try:
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f)
            step_logger.info(f"[ClassificationCache] Saved {len(self.cache)} embeddings to {self.cache_path}")
        except Exception as e:
            step_logger.error(f"[ClassificationCache] Failed to save: {e}")
    
    def __len__(self):
        return len(self.cache)


class ChromaClassificationStore:
    """
    ChromaDB-based store for system classification embeddings.
    
    Used to match incoming queries against known patterns like
    clarification phrases. Uses JSON cache to avoid recalculating embeddings.
    """
    
    COLLECTION_NAME = "query_classification"
    
    def __init__(
        self, 
        persist_directory: str = "data/chroma",
        embedding_provider=None,
        cache_path: str = "data/classification_embeddings_cache.json"
    ):
        """
        Initialize ChromaDB store with optional embedding cache.
        
        Args:
            persist_directory: Where to persist ChromaDB data
            embedding_provider: Provider to generate embeddings
            cache_path: Path for embedding cache JSON file
        """
        self._persist_dir = persist_directory
        self._embedding_provider = embedding_provider
        self._cache = ClassificationEmbeddingCache(cache_path)
        
        # Ensure directory exists
        Path(persist_directory).mkdir(parents=True, exist_ok=True)
        
        # Initialize ChromaDB client with persistence
        self._client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Get or create collection (using cosine similarity)
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )
        
        step_logger.info(
            f"[ChromaStore] Initialized with {self._collection.count()} embeddings, "
            f"{len(self._cache)} cached"
        )
    
    def set_embedding_provider(self, provider):
        """Set the embedding provider after initialization."""
        self._embedding_provider = provider
    
    def _get_embedding(self, phrase: str) -> List[float]:
        """Get embedding, using cache when available."""
        # Check cache first
        cached = self._cache.get(phrase)
        if cached is not None:
            return cached
        
        # Generate new embedding
        if not self._embedding_provider:
            raise ValueError("Embedding provider not set")
        
        embedding = self._embedding_provider.get_embedding(phrase)
        
        # Cache it
        self._cache.set(phrase, embedding)
        
        return embedding
    
    def add_classification_embedding(
        self, 
        phrase: str, 
        category: str = "clarification",
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Add a classification phrase with its embedding.
        Uses cache to avoid recalculating embeddings.
        """
        # Generate embedding (uses cache)
        embedding = self._get_embedding(phrase)
        
        # Create ID from phrase
        doc_id = f"{category}_{hash(phrase) % 10000000}"
        
        # Check if already exists in ChromaDB
        try:
            existing = self._collection.get(ids=[doc_id])
            if existing and existing['ids']:
                step_logger.debug(f"[ChromaStore] Phrase already in collection: '{phrase}'")
                return doc_id
        except Exception:
            pass
        
        # Build metadata
        doc_metadata = {
            "category": category,
            "phrase": phrase,
            **(metadata or {})
        }
        
        # Add to collection
        self._collection.add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[phrase],
            metadatas=[doc_metadata]
        )
        
        step_logger.debug(f"[ChromaStore] Added embedding for: '{phrase}'")
        return doc_id
    
    def find_similar(
        self, 
        query: str, 
        top_k: int = 3,
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Find similar phrases to the query.
        """
        # Generate query embedding (uses cache)
        query_embedding = self._get_embedding(query)
        
        # Build where clause
        where_clause = {"category": category} if category else None
        
        # Query collection
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_clause,
            include=["documents", "metadatas", "distances"]
        )
        
        # Process results
        matches = []
        if results and results.get("ids") and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                distance = results["distances"][0][i] if results.get("distances") else 0
                similarity = 1 - distance
                
                matches.append({
                    "id": doc_id,
                    "phrase": results["documents"][0][i] if results.get("documents") else "",
                    "category": results["metadatas"][0][i].get("category", "") if results.get("metadatas") else "",
                    "similarity": similarity
                })
        
        return matches
    
    def seed_defaults(self, force: bool = False) -> int:
        """
        Seed the store with default clarification phrases.
        Uses cache to avoid recalculating embeddings.
        """
        if not self._embedding_provider:
            step_logger.warning("[ChromaStore] Cannot seed: no embedding provider")
            return 0
        
        current_count = self._collection.count()
        
        if current_count > 0 and not force:
            step_logger.info(f"[ChromaStore] Already seeded with {current_count} embeddings, skipping")
            return 0
        
        if force and current_count > 0:
            self._collection.delete(where={"category": "clarification"})
            step_logger.info("[ChromaStore] Cleared existing clarification embeddings")
        
        # Add default phrases (cache reduces API calls)
        count = 0
        for phrase in DEFAULT_CLARIFICATION_PHRASES:
            try:
                self.add_classification_embedding(phrase, category="clarification")
                count += 1
            except Exception as e:
                step_logger.warning(f"[ChromaStore] Failed to add '{phrase}': {e}")
        
        # Save cache after seeding
        self._cache.save()
        
        step_logger.info(f"[ChromaStore] Seeded {count} phrases, cache has {len(self._cache)} entries")
        return count
    
    def count(self) -> int:
        """Return total number of embeddings in the store."""
        return self._collection.count()
    
    def clear(self):
        """Clear all embeddings from the store."""
        self._client.delete_collection(self.COLLECTION_NAME)
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )
        step_logger.info("[ChromaStore] Cleared all embeddings")
