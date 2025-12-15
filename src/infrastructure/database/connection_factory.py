"""
Database connection factory.
Creates appropriate database connection based on configuration.
"""
import os
from typing import Optional

from src.infrastructure.database.interface import DatabaseConnection
from src.utils.logger import step_logger


# Singleton instance
_connection: Optional[DatabaseConnection] = None


def get_database_connection(config: Optional[dict] = None) -> DatabaseConnection:
    """
    Get database connection based on configuration.
    
    Priority:
    1. DATABASE_TYPE environment variable
    2. config['database']['type']
    3. Default to 'sqlite'
    
    Args:
        config: Configuration dict (optional, will load from file if not provided)
        
    Returns:
        DatabaseConnection instance (singleton)
    """
    global _connection
    
    if _connection is not None:
        return _connection
    
    # Determine database type (mariadb is default)
    db_type = os.getenv("DATABASE_TYPE")
    
    if db_type is None and config:
        db_type = config.get("database", {}).get("type", "mariadb")
    
    db_type = db_type or "mariadb"
    
    step_logger.info(f"[Database] Initializing connection type: {db_type}")
    
    if db_type == "mariadb":
        _connection = _create_mariadb_connection(config)
    else:
        _connection = _create_sqlite_connection(config)
    
    return _connection


def _create_mariadb_connection(config: Optional[dict]) -> DatabaseConnection:
    """Create MariaDB connection from config or environment."""
    from src.infrastructure.database.mariadb_connection import MariaDBConnection
    from src.infrastructure.database.mariadb_schema import init_mariadb_schema
    
    # Try URI from environment first
    uri = os.getenv("MARIADB_URI")
    
    if uri:
        connection = MariaDBConnection.get_instance(uri=uri)
    elif config and "database" in config and "mariadb" in config["database"]:
        # Build from config
        mariadb_config = config["database"]["mariadb"]
        connection = MariaDBConnection.get_instance(
            host=mariadb_config.get("host", "mariadb"),
            port=mariadb_config.get("port", 3306),
            database=mariadb_config.get("database", "coloraria"),
            user=mariadb_config.get("user", "coloraria_user"),
            password=os.getenv("MARIADB_PASSWORD", mariadb_config.get("password", "")),
            pool_size=mariadb_config.get("pool_size", 10),
            pool_recycle=mariadb_config.get("pool_recycle", 3600)
        )
    else:
        # Default fallback
        connection = MariaDBConnection.get_instance()
    
    # Auto-initialize schema (creates tables if they don't exist)
    try:
        init_mariadb_schema(connection)
    except Exception as e:
        step_logger.warning(f"[Database] Schema init warning: {e}")
    
    return connection


def _create_sqlite_connection(config: Optional[dict]) -> DatabaseConnection:
    """Create SQLite connection from config."""
    from src.infrastructure.database.sqlite_adapter import SQLiteConnectionAdapter
    
    db_path = "data/coloraria.db"
    
    if config and "database" in config and "sqlite" in config["database"]:
        db_path = config["database"]["sqlite"].get("path", db_path)
    
    return SQLiteConnectionAdapter.get_instance(db_path)


def reset_connection():
    """Reset connection singleton (for testing)."""
    global _connection
    if _connection:
        _connection.close()
    _connection = None


def init_database_schema(connection: DatabaseConnection, db_type: str = "mariadb"):
    """
    Initialize database schema.
    
    Args:
        connection: Database connection
        db_type: 'sqlite' or 'mariadb'
    """
    if db_type == "mariadb":
        from src.infrastructure.database.mariadb_schema import init_mariadb_schema
        init_mariadb_schema(connection)
    else:
        # SQLite uses existing init_database function
        from src.infrastructure.sqlite.base import init_database
        init_database()
