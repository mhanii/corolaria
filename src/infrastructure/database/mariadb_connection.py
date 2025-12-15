"""
MariaDB connection implementation using SQLAlchemy.
Provides connection pooling and thread-safe database access.
"""
import os
from typing import Optional, List, Any
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool

from src.infrastructure.database.interface import DatabaseConnection
from src.utils.logger import step_logger


class MariaDBConnection(DatabaseConnection):
    """
    Thread-safe MariaDB connection with connection pooling.
    
    Uses SQLAlchemy's QueuePool for efficient connection management
    across multiple concurrent requests.
    """
    
    _instance: Optional['MariaDBConnection'] = None
    
    def __init__(
        self,
        uri: Optional[str] = None,
        host: str = "mariadb",
        port: int = 3306,
        database: str = "coloraria",
        user: str = "coloraria_user",
        password: str = "",
        pool_size: int = 10,
        pool_recycle: int = 3600
    ):
        """
        Initialize MariaDB connection pool.
        
        Args:
            uri: Full connection URI (overrides other params)
            host: Database host
            port: Database port
            database: Database name
            user: Database user
            password: Database password
            pool_size: Connection pool size
            pool_recycle: Seconds before connection recycling
        """
        # Build URI from params if not provided
        if uri:
            self._uri = uri
        else:
            # Get password from environment if not provided
            password = password or os.getenv("MARIADB_PASSWORD", "")
            self._uri = f"mariadb+pymysql://{user}:{password}@{host}:{port}/{database}"
        
        # Create engine with connection pooling
        self._engine = create_engine(
            self._uri,
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=pool_size * 2,
            pool_recycle=pool_recycle,
            pool_pre_ping=True,  # Verify connections before use
            echo=False
        )
        
        # Create scoped session factory (thread-local sessions)
        self._session_factory = sessionmaker(bind=self._engine, autocommit=False)
        self._Session = scoped_session(self._session_factory)
        
        step_logger.info(f"[MariaDB] Connection pool initialized (size={pool_size})")
    
    @classmethod
    def get_instance(
        cls,
        uri: Optional[str] = None,
        **kwargs
    ) -> 'MariaDBConnection':
        """
        Get singleton instance of MariaDB connection.
        
        Args:
            uri: Connection URI (from env MARIADB_URI if not provided)
            **kwargs: Additional connection parameters
            
        Returns:
            MariaDBConnection singleton
        """
        if cls._instance is None:
            # Try to get URI from environment
            uri = uri or os.getenv("MARIADB_URI")
            cls._instance = cls(uri=uri, **kwargs)
        return cls._instance
    
    @classmethod
    def reset_instance(cls):
        """Reset singleton (for testing)."""
        if cls._instance:
            cls._instance.close()
        cls._instance = None
    
    def execute(self, query: str, params: tuple = ()) -> Any:
        """Execute query with auto-commit."""
        session = self._Session()
        try:
            result = session.execute(text(query), self._params_to_dict(query, params))
            session.commit()
            return result
        except Exception as e:
            session.rollback()
            step_logger.error(f"[MariaDB] Query failed: {e}")
            raise
        finally:
            self._Session.remove()
    
    def executemany(self, query: str, params_list: list) -> Any:
        """Execute query with multiple parameter sets."""
        session = self._Session()
        try:
            # Convert list of tuples to list of dicts
            dict_params = [self._params_to_dict(query, p) for p in params_list]
            result = session.execute(text(query), dict_params)
            session.commit()
            return result
        except Exception as e:
            session.rollback()
            step_logger.error(f"[MariaDB] Batch query failed: {e}")
            raise
        finally:
            self._Session.remove()
    
    def fetchone(self, query: str, params: tuple = ()) -> Optional[dict]:
        """Fetch single row as dict."""
        session = self._Session()
        try:
            result = session.execute(text(query), self._params_to_dict(query, params))
            row = result.fetchone()
            if row:
                return dict(row._mapping)
            return None
        finally:
            self._Session.remove()
    
    def fetchall(self, query: str, params: tuple = ()) -> List[dict]:
        """Fetch all rows as list of dicts."""
        session = self._Session()
        try:
            result = session.execute(text(query), self._params_to_dict(query, params))
            return [dict(row._mapping) for row in result.fetchall()]
        finally:
            self._Session.remove()
    
    @contextmanager
    def transaction(self):
        """Context manager for explicit transactions."""
        session = self._Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            step_logger.error(f"[MariaDB] Transaction failed: {e}")
            raise
        finally:
            self._Session.remove()
    
    def close(self):
        """Close the connection pool."""
        if self._engine:
            self._engine.dispose()
            step_logger.info("[MariaDB] Connection pool closed")
    
    @property
    def placeholder(self) -> str:
        """MariaDB uses :name for SQLAlchemy text() queries."""
        return ":p"
    
    def _params_to_dict(self, query: str, params: tuple) -> dict:
        """
        Convert positional parameters to named parameters for SQLAlchemy.
        
        Replaces ? with :p0, :p1, etc. and creates corresponding dict.
        """
        if not params:
            return {}
        
        # Create dict with :p0, :p1, etc.
        return {f"p{i}": v for i, v in enumerate(params)}
    
    def get_raw_connection(self):
        """Get raw database connection for operations that need it."""
        return self._engine.connect()
