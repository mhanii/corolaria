"""
LangGraph checkpointer for MariaDB/MySQL persistence.
Manages PyMySQLSaver for persisting graph state across sessions.
"""
import os
from typing import Optional, Union
from src.utils.logger import step_logger


# Singleton checkpointer instance (can be either SQLite or MySQL)
_checkpointer = None


def get_checkpointer(db_type: str = "mariadb", db_uri: Optional[str] = None):
    """
    Get or create the checkpointer singleton based on database type.
    
    Args:
        db_type: 'sqlite' or 'mariadb'
        db_uri: Connection string (optional, will use env vars if not provided)
        
    Returns:
        SqliteSaver or PyMySQLSaver instance
    """
    global _checkpointer
    
    if _checkpointer is not None:
        return _checkpointer
    
    # Get db_type from environment if not specified
    db_type = os.getenv("DATABASE_TYPE", db_type)
    
    if db_type == "mariadb":
        _checkpointer = _create_mariadb_checkpointer(db_uri)
    else:
        _checkpointer = _create_sqlite_checkpointer(db_uri)
    
    return _checkpointer


def _create_mariadb_checkpointer(uri: Optional[str] = None):
    """Create MariaDB checkpointer using PyMySQLSaver."""
    try:
        # Correct import path for langgraph-checkpoint-mysql
        from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver
        
        # Get URI from environment if not provided
        uri = uri or os.getenv("MARIADB_URI")
        
        if not uri:
            # Build from individual components
            host = os.getenv("MARIADB_HOST", "mariadb")
            port = os.getenv("MARIADB_PORT", "3306")
            db = os.getenv("MARIADB_DATABASE", "coloraria")
            user = os.getenv("MARIADB_USER", "coloraria_user")
            password = os.getenv("MARIADB_PASSWORD", "")
            uri = f"mysql+pymysql://{user}:{password}@{host}:{port}/{db}"
        
        step_logger.info(f"[Checkpointer] Initializing PyMySQLSaver")
        
        # from_conn_string returns a context manager/generator
        # We need to enter it to get the actual saver
        cm = PyMySQLSaver.from_conn_string(uri)
        checkpointer = cm.__enter__()
        
        # Setup creates the checkpoint tables if needed
        checkpointer.setup()
        
        step_logger.info("[Checkpointer] PyMySQLSaver initialized")
        return checkpointer
        
    except ImportError as e:
        step_logger.warning(f"[Checkpointer] langgraph-checkpoint-mysql not installed: {e}")
        step_logger.warning("[Checkpointer] Falling back to SQLite")
        return _create_sqlite_checkpointer(None)
    except Exception as e:
        step_logger.error(f"[Checkpointer] Failed to initialize MariaDB checkpointer: {e}")
        step_logger.warning("[Checkpointer] Falling back to SQLite")
        return _create_sqlite_checkpointer(None)


def _create_sqlite_checkpointer(db_path: Optional[str] = None):
    """Create SQLite checkpointer (fallback)."""
    import sqlite3
    from langgraph.checkpoint.sqlite import SqliteSaver
    
    db_path = db_path or os.getenv("SQLITE_PATH", "data/coloraria.db")
    
    step_logger.info(f"[Checkpointer] Initializing SqliteSaver: {db_path}")
    
    connection = sqlite3.connect(db_path, check_same_thread=False)
    checkpointer = SqliteSaver(connection)
    
    step_logger.info("[Checkpointer] SqliteSaver initialized")
    return checkpointer


def close_checkpointer():
    """Close the checkpointer connection."""
    global _checkpointer
    
    if _checkpointer is not None:
        # Different checkpointers have different close methods
        try:
            if hasattr(_checkpointer, 'close'):
                _checkpointer.close()
            elif hasattr(_checkpointer, '_connection'):
                _checkpointer._connection.close()
        except Exception as e:
            step_logger.warning(f"[Checkpointer] Error closing: {e}")
    
    _checkpointer = None
    step_logger.info("[Checkpointer] Checkpointer closed")


def reset_checkpointer():
    """Reset checkpointer singleton (for testing)."""
    close_checkpointer()
