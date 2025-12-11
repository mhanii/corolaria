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
    SQLite file-based cache for classification embeddings.
    Uses binary blob storage for efficiency.
    """
    
    def __init__(self, cache_path: str = "data/classification_embeddings_cache.db"):
        import sqlite3
        import struct
        from datetime import datetime
        
        self._struct = struct
        self._datetime = datetime
        
        # Ensure .db extension for SQLite
        if cache_path.endswith('.json'):
            cache_path = cache_path.replace('.json', '.db')
        
        self.cache_path = cache_path
        self._connection: Optional[sqlite3.Connection] = None
        self._ensure_database()
    
    def _ensure_database(self):
        """Ensure database and schema exist."""
        import sqlite3
        
        # Ensure directory exists
        cache_dir = os.path.dirname(self.cache_path)
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
        
        conn = self._get_connection()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS embedding_cache (
                key TEXT PRIMARY KEY,
                embedding BLOB NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_embedding_cache_key ON embedding_cache(key);
        """)
        conn.commit()
        
        # Log entry count
        cursor = conn.execute("SELECT COUNT(*) FROM embedding_cache")
        count = cursor.fetchone()[0]
        if count > 0:
            step_logger.info(f"[ClassificationCache] Loaded {count} cached embeddings")
    
    def _get_connection(self):
        """Get or create database connection."""
        import sqlite3
        if self._connection is None:
            self._connection = sqlite3.connect(self.cache_path, check_same_thread=False)
        return self._connection
    
    def _pack_embedding(self, embedding: List[float]) -> bytes:
        """Pack embedding list to binary blob (float32)."""
        return self._struct.pack(f'{len(embedding)}f', *embedding)
    
    def _unpack_embedding(self, blob: bytes) -> List[float]:
        """Unpack binary blob to embedding list."""
        count = len(blob) // 4  # 4 bytes per float32
        return list(self._struct.unpack(f'{count}f', blob))
    
    def get(self, phrase: str) -> Optional[List[float]]:
        """Get cached embedding for phrase."""
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT embedding FROM embedding_cache WHERE key = ?",
            (phrase,)
        )
        row = cursor.fetchone()
        if row:
            return self._unpack_embedding(row[0])
        return None
    
    def set(self, phrase: str, embedding: List[float]):
        """Cache an embedding."""
        conn = self._get_connection()
        blob = self._pack_embedding(embedding)
        conn.execute(
            """
            INSERT OR REPLACE INTO embedding_cache (key, embedding, created_at)
            VALUES (?, ?, ?)
            """,
            (phrase, blob, self._datetime.now().isoformat())
        )
    
    def save(self):
        """Persist cache to disk."""
        if self._connection:
            self._connection.commit()
            step_logger.info(f"[ClassificationCache] Saved to {self.cache_path}")
    
    def __len__(self):
        conn = self._get_connection()
        cursor = conn.execute("SELECT COUNT(*) FROM embedding_cache")
        return cursor.fetchone()[0]


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
