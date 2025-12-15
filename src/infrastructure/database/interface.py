"""
Database connection interface.
Abstract base class for database connections that can be implemented
by SQLite, MariaDB, or other backends.
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Any
from contextlib import contextmanager


class DatabaseConnection(ABC):
    """
    Abstract interface for database operations.
    
    Provides a unified API for database operations regardless of backend.
    Each implementation handles connection pooling and thread safety.
    """
    
    @abstractmethod
    def execute(self, query: str, params: tuple = ()) -> Any:
        """
        Execute a query with auto-commit.
        
        Args:
            query: SQL query (use %s for MariaDB, ? for SQLite)
            params: Query parameters
            
        Returns:
            Cursor-like object with results
        """
        pass
    
    @abstractmethod
    def executemany(self, query: str, params_list: list) -> Any:
        """
        Execute a query with multiple parameter sets.
        
        Args:
            query: SQL query
            params_list: List of parameter tuples
            
        Returns:
            Cursor-like object with results
        """
        pass
    
    @abstractmethod
    def fetchone(self, query: str, params: tuple = ()) -> Optional[dict]:
        """
        Execute query and fetch one result as dict.
        
        Args:
            query: SQL query
            params: Query parameters
            
        Returns:
            Dict with column names as keys, or None
        """
        pass
    
    @abstractmethod
    def fetchall(self, query: str, params: tuple = ()) -> List[dict]:
        """
        Execute query and fetch all results as list of dicts.
        
        Args:
            query: SQL query
            params: Query parameters
            
        Returns:
            List of dicts with column names as keys
        """
        pass
    
    @abstractmethod
    @contextmanager
    def transaction(self):
        """
        Context manager for explicit transactions.
        
        Yields:
            Connection or session for transaction scope
        """
        pass
    
    @abstractmethod
    def close(self):
        """Close the connection/pool."""
        pass
    
    @property
    @abstractmethod
    def placeholder(self) -> str:
        """
        Get the parameter placeholder for this database.
        
        Returns:
            '?' for SQLite, '%s' for MariaDB
        """
        pass
