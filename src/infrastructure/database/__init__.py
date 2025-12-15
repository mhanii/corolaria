"""
Database infrastructure package.
Provides abstract database interface and implementations for SQLite and MariaDB.
"""
from src.infrastructure.database.interface import DatabaseConnection
from src.infrastructure.database.connection_factory import (
    get_database_connection,
    reset_connection,
    init_database_schema
)

__all__ = [
    "DatabaseConnection",
    "get_database_connection",
    "reset_connection",
    "init_database_schema"
]
