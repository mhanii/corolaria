"""
SQLite connection adapter.
Wraps existing SQLiteConnection to implement DatabaseConnection interface.
"""
from typing import Optional, List, Any
from contextlib import contextmanager

from src.infrastructure.database.interface import DatabaseConnection
from src.infrastructure.sqlite.connection import SQLiteConnection as LegacySQLiteConnection
from src.utils.logger import step_logger


class SQLiteConnectionAdapter(DatabaseConnection):
    """
    Adapter that wraps legacy SQLiteConnection to implement DatabaseConnection interface.
    
    Allows existing SQLite code to work with the new abstraction layer.
    """
    
    def __init__(self, legacy_connection: LegacySQLiteConnection):
        """
        Initialize adapter with legacy connection.
        
        Args:
            legacy_connection: Existing SQLiteConnection instance
        """
        self._connection = legacy_connection
    
    @classmethod
    def get_instance(cls, db_path: str = "data/coloraria.db") -> 'SQLiteConnectionAdapter':
        """Get instance wrapping legacy SQLiteConnection singleton."""
        legacy = LegacySQLiteConnection.get_instance(db_path)
        return cls(legacy)
    
    def execute(self, query: str, params: tuple = ()) -> Any:
        """Execute query with auto-commit."""
        return self._connection.execute(query, params)
    
    def executemany(self, query: str, params_list: list) -> Any:
        """Execute query with multiple parameter sets."""
        return self._connection.executemany(query, params_list)
    
    def fetchone(self, query: str, params: tuple = ()) -> Optional[dict]:
        """Fetch single row as dict."""
        row = self._connection.fetchone(query, params)
        if row:
            # sqlite3.Row can be converted to dict
            return dict(row)
        return None
    
    def fetchall(self, query: str, params: tuple = ()) -> List[dict]:
        """Fetch all rows as list of dicts."""
        rows = self._connection.fetchall(query, params)
        return [dict(row) for row in rows]
    
    @contextmanager
    def transaction(self):
        """Context manager for explicit transactions."""
        # Use existing cursor context manager
        with self._connection.cursor() as cursor:
            yield cursor
    
    def close(self):
        """Close connection."""
        self._connection.close_all()
    
    @property
    def placeholder(self) -> str:
        """SQLite uses ? for parameters."""
        return "?"
    
    @property
    def legacy_connection(self) -> LegacySQLiteConnection:
        """Access underlying legacy connection for compatibility."""
        return self._connection
