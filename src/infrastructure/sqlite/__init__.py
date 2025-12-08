"""
SQLite infrastructure package.
Provides database connection, schema, and repositories for persistence.
"""
from src.infrastructure.sqlite.connection import SQLiteConnection
from src.infrastructure.sqlite.base import init_database

__all__ = ["SQLiteConnection", "init_database"]
