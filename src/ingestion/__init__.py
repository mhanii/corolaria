"""
Coloraria Ingestion Service Module.

This module provides the ingestion pipeline for processing legal documents
and loading them into the Neo4j graph database.
"""

from .result import IngestionResult, RollbackResult
from .ingestion_context import IngestionContext
from .config import IngestionConfig

# Lazy imports for main.py to avoid RuntimeWarning when running with python -m
def run_ingestion(*args, **kwargs):
    from .main import run_ingestion as _run_ingestion
    return _run_ingestion(*args, **kwargs)

def ingestion_lifecycle(*args, **kwargs):
    from .main import ingestion_lifecycle as _ingestion_lifecycle
    return _ingestion_lifecycle(*args, **kwargs)

__all__ = [
    "run_ingestion",
    "ingestion_lifecycle",
    "IngestionResult",
    "RollbackResult",
    "IngestionContext",
    "IngestionConfig",
]
