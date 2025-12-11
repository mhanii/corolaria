"""
SQLite-based embedding cache with efficient binary blob storage.

Stores embeddings as packed float32 blobs for ~75% space savings vs JSON.

Thread-safe implementation using:
- WAL mode for concurrent read/write
- Threading lock for cursor safety
- Batch operations to minimize lock contention
- Direct indexed queries (no pre-loading into RAM)
"""
import sqlite3
import struct
import os
import threading
from datetime import datetime
from typing import List, Optional, Dict
from src.domain.interfaces.embedding_cache import EmbeddingCache
from src.utils.logger import step_logger


class SQLiteEmbeddingCache(EmbeddingCache):
    """
    Thread-safe SQLite-based cache implementation using binary blob storage.
    
    Uses WAL mode and threading locks for safe concurrent access.
    Supports batch operations to minimize lock contention in multi-threaded scenarios.
    
    Embeddings are stored as packed float32 arrays (4 bytes per float)
    instead of JSON text (~12-15 bytes per float character representation).
    
    SQLite's internal page cache handles memory management - we do NOT
    preload data into a Python dict.
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
        self._lock = threading.Lock()  # Thread safety for cursor operations
        self._dirty = False  # Track if there are uncommitted changes
        self._ensure_database()
    
    def _ensure_database(self):
        """Ensure database and schema exist with WAL mode."""
        # Ensure directory exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        
        with self._lock:
            conn = self._get_connection()
            
            # Enable WAL mode for better concurrent read/write
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")  # Faster writes, still safe
            conn.execute("PRAGMA cache_size=-64000")   # 64MB page cache
            
            # Initialize schema
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
            # check_same_thread=False allows multi-thread access
            # We handle thread safety with self._lock
            self._connection = sqlite3.connect(
                self.db_path, 
                check_same_thread=False,
                timeout=30.0  # Wait up to 30s for locks
            )
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
        """Retrieve embedding by key (hash). Thread-safe."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT embedding FROM embedding_cache WHERE key = ?",
                (key,)
            )
            row = cursor.fetchone()
            if row:
                return self._unpack_embedding(row[0])
            return None
    
    def get_batch(self, keys: List[str]) -> Dict[str, List[float]]:
        """
        Retrieve multiple embeddings in a single query. Thread-safe.
        
        Args:
            keys: List of cache keys (hashes)
            
        Returns:
            Dict mapping found keys to embeddings. Keys not in cache are omitted.
        """
        if not keys:
            return {}
        
        with self._lock:
            conn = self._get_connection()
            
            # Use parameterized query with IN clause
            placeholders = ','.join('?' * len(keys))
            cursor = conn.execute(
                f"SELECT key, embedding FROM embedding_cache WHERE key IN ({placeholders})",
                keys
            )
            
            result = {}
            for row in cursor.fetchall():
                result[row[0]] = self._unpack_embedding(row[1])
            
            return result
    
    def set(self, key: str, embedding: List[float]):
        """Store embedding by key (hash). Thread-safe."""
        with self._lock:
            conn = self._get_connection()
            blob = self._pack_embedding(embedding)
            conn.execute(
                """
                INSERT OR REPLACE INTO embedding_cache (key, embedding, created_at)
                VALUES (?, ?, ?)
                """,
                (key, blob, datetime.now().isoformat())
            )
            self._dirty = True  # Mark for commit
    
    def set_batch(self, items: Dict[str, List[float]]):
        """
        Store multiple embeddings in a single transaction. Thread-safe.
        
        Args:
            items: Dict mapping keys to embeddings
        """
        if not items:
            return
        
        with self._lock:
            conn = self._get_connection()
            now = datetime.now().isoformat()
            
            # Prepare batch data
            batch_data = [
                (key, self._pack_embedding(embedding), now)
                for key, embedding in items.items()
            ]
            
            # Execute batch insert
            conn.executemany(
                """
                INSERT OR REPLACE INTO embedding_cache (key, embedding, created_at)
                VALUES (?, ?, ?)
                """,
                batch_data
            )
            self._dirty = True  # Mark for commit
    
    def save(self):
        """Persist cache to storage (commit transaction). Thread-safe. No-op if nothing to commit."""
        with self._lock:
            if self._connection and self._dirty:
                self._connection.commit()
                self._dirty = False
                step_logger.info(f"Saved embedding cache to {self.db_path}")
    
    def close(self):
        """Close database connection. Thread-safe."""
        with self._lock:
            if self._connection:
                self._connection.close()
                self._connection = None
    
    def __del__(self):
        """Ensure connection is closed on garbage collection."""
        self.close()
