"""
SQLite-based embedding cache with efficient binary blob storage.

Stores embeddings as packed float32 blobs for ~75% space savings vs JSON.
"""
import sqlite3
import struct
import os
from datetime import datetime
from typing import List, Optional
from src.domain.interfaces.embedding_cache import EmbeddingCache
from src.utils.logger import step_logger


class SQLiteEmbeddingCache(EmbeddingCache):
    """
    SQLite-based cache implementation using binary blob storage.
    
    Embeddings are stored as packed float32 arrays (4 bytes per float)
    instead of JSON text (~12-15 bytes per float character representation).
    """
    
    SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS embedding_cache (
        key TEXT PRIMARY KEY,
        embedding BLOB NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_embedding_cache_key ON embedding_cache(key);
    """
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._connection: Optional[sqlite3.Connection] = None
        self._ensure_database()
    
    def _ensure_database(self):
        """Ensure database and schema exist."""
        # Ensure directory exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        
        # Initialize schema
        conn = self._get_connection()
        conn.executescript(self.SCHEMA_SQL)
        conn.commit()
        
        # Get entry count for logging
        cursor = conn.execute("SELECT COUNT(*) FROM embedding_cache")
        count = cursor.fetchone()[0]
        if count > 0:
            step_logger.info(f"Loaded embedding cache from {self.db_path} ({count} entries)")
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._connection is None:
            self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        return self._connection
    
    @staticmethod
    def _pack_embedding(embedding: List[float]) -> bytes:
        """Pack embedding list to binary blob (float32)."""
        return struct.pack(f'{len(embedding)}f', *embedding)
    
    @staticmethod
    def _unpack_embedding(blob: bytes) -> List[float]:
        """Unpack binary blob to embedding list."""
        count = len(blob) // 4  # 4 bytes per float32
        return list(struct.unpack(f'{count}f', blob))
    
    def get(self, key: str) -> Optional[List[float]]:
        """Retrieve embedding by key (hash)."""
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT embedding FROM embedding_cache WHERE key = ?",
            (key,)
        )
        row = cursor.fetchone()
        if row:
            return self._unpack_embedding(row[0])
        return None
    
    def set(self, key: str, embedding: List[float]):
        """Store embedding by key (hash)."""
        conn = self._get_connection()
        blob = self._pack_embedding(embedding)
        conn.execute(
            """
            INSERT OR REPLACE INTO embedding_cache (key, embedding, created_at)
            VALUES (?, ?, ?)
            """,
            (key, blob, datetime.now().isoformat())
        )
        # Note: commit happens in save() for batch efficiency
    
    def save(self):
        """Persist cache to storage (commit transaction)."""
        if self._connection:
            self._connection.commit()
            step_logger.info(f"Saved embedding cache to {self.db_path}")
    
    def close(self):
        """Close database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None
    
    def __del__(self):
        """Ensure connection is closed on garbage collection."""
        self.close()
