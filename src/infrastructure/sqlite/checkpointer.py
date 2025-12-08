"""
LangGraph checkpointer for SQLite persistence.
Manages SqliteSaver for persisting graph state across sessions.
"""
import sqlite3
from typing import Optional
from langgraph.checkpoint.sqlite import SqliteSaver

from src.utils.logger import step_logger


# Singleton checkpointer instance
_checkpointer: Optional[SqliteSaver] = None
_connection: Optional[sqlite3.Connection] = None


def get_checkpointer(db_path: str = "data/coloraria.db") -> SqliteSaver:
    """
    Get or create the SQLite checkpointer singleton.
    
    Uses the same database as other persistence for simplicity.
    LangGraph will create its own tables for checkpoint storage.
    
    Args:
        db_path: Path to SQLite database file
        
    Returns:
        SqliteSaver instance
    """
    global _checkpointer, _connection
    
    if _checkpointer is None:
        step_logger.info(f"[Checkpointer] Initializing SqliteSaver: {db_path}")
        
        # Create a persistent connection for the checkpointer
        _connection = sqlite3.connect(db_path, check_same_thread=False)
        _checkpointer = SqliteSaver(_connection)
        
        step_logger.info("[Checkpointer] SqliteSaver initialized")
    
    return _checkpointer


def close_checkpointer():
    """Close the checkpointer connection."""
    global _checkpointer, _connection
    
    if _connection is not None:
        _connection.close()
        _connection = None
    
    _checkpointer = None
    step_logger.info("[Checkpointer] SqliteSaver closed")
