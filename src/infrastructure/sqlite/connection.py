"""
SQLite connection manager.
Provides thread-safe connection pooling for concurrent access.
"""
import sqlite3
import threading
import os
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

from src.utils.logger import step_logger


class SQLiteConnection:
    """
    Thread-safe SQLite connection manager.
    
    Uses thread-local storage to provide separate connections per thread,
    enabling safe concurrent access from multiple API requests.
    """
    
    _instance: Optional['SQLiteConnection'] = None
    _lock = threading.Lock()
    
    def __init__(self, db_path: str = "data/coloraria.db"):
        """
        Initialize SQLite connection manager.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._local = threading.local()
        
        # Ensure directory exists
        db_dir = Path(db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        
        step_logger.info(f"[SQLite] Connection manager initialized: {db_path}")
    
    @classmethod
    def get_instance(cls, db_path: str = "data/coloraria.db") -> 'SQLiteConnection':
        """
        Get singleton instance of connection manager.
        
        Args:
            db_path: Path to SQLite database file
            
        Returns:
            SQLiteConnection singleton
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(db_path)
        return cls._instance
    
    def get_connection(self) -> sqlite3.Connection:
        """
        Get thread-local database connection.
        
        Returns:
            SQLite connection for current thread
        """
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0
            )
            # Enable foreign keys
            self._local.connection.execute("PRAGMA foreign_keys = ON")
            # Return rows as dictionaries
            self._local.connection.row_factory = sqlite3.Row
            
        return self._local.connection
    
    @contextmanager
    def cursor(self):
        """
        Context manager for database cursor with auto-commit.
        
        Yields:
            Database cursor
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            step_logger.error(f"[SQLite] Transaction failed: {e}")
            raise
        finally:
            cursor.close()
    
    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """
        Execute a query with auto-commit.
        
        Args:
            query: SQL query
            params: Query parameters
            
        Returns:
            Cursor with results
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        return cursor
    
    def executemany(self, query: str, params_list: list) -> sqlite3.Cursor:
        """
        Execute a query with multiple parameter sets.
        
        Args:
            query: SQL query
            params_list: List of parameter tuples
            
        Returns:
            Cursor with results
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.executemany(query, params_list)
        conn.commit()
        return cursor
    
    def fetchone(self, query: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """
        Execute query and fetch one result.
        
        Args:
            query: SQL query
            params: Query parameters
            
        Returns:
            Single row or None
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchone()
    
    def fetchall(self, query: str, params: tuple = ()) -> list:
        """
        Execute query and fetch all results.
        
        Args:
            query: SQL query
            params: Query parameters
            
        Returns:
            List of rows
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchall()
    
    def close_thread_connection(self):
        """Close the connection for the current thread."""
        if hasattr(self._local, 'connection') and self._local.connection:
            self._local.connection.close()
            self._local.connection = None
    
    def close_all(self):
        """Close the thread-local connection (for cleanup)."""
        self.close_thread_connection()
