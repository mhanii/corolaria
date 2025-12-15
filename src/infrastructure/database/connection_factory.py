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
    from urllib.parse import quote_plus
    from src.infrastructure.database.mariadb_connection import MariaDBConnection
    from src.infrastructure.database.mariadb_schema import init_mariadb_schema
    
    # Try explicit URI from environment first
    uri = os.getenv("MARIADB_URI")
    
    if not uri:
        # Build URI dynamically from individual env vars (with URL encoding for special chars)
        host = os.getenv("MARIADB_HOST", "mariadb")
        port = os.getenv("MARIADB_PORT", "3306")
        database = os.getenv("MARIADB_DATABASE", "coloraria")
        user = os.getenv("MARIADB_USER", "coloraria_user")
        password = os.getenv("MARIADB_PASSWORD", "")
        
        # URL-encode the password to handle special characters like @, #, :, etc.
        encoded_password = quote_plus(password)
        
        uri = f"mysql+pymysql://{user}:{encoded_password}@{host}:{port}/{database}"
        step_logger.info(f"[Database] Built MariaDB URI: mysql+pymysql://{user}:***@{host}:{port}/{database}")
    
    connection = MariaDBConnection.get_instance(uri=uri)
    
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
