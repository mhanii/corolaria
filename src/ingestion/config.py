"""
Ingestion Service Configuration.

Dataclass-based configuration for the ingestion pipeline.
"""

from dataclasses import dataclass, field
from typing import Optional
import os
from dotenv import load_dotenv


@dataclass
class EmbeddingConfig:
    """Configuration for embedding generation."""
    model_name: str = "models/gemini-embedding-001"
    dimensions: int = 768
    similarity: str = "cosine"
    task_type: str = "RETRIEVAL_DOCUMENT"


@dataclass
class Neo4jConfig:
    """Configuration for Neo4j connection."""
    uri: str = field(default_factory=lambda: os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    user: str = field(default_factory=lambda: os.getenv("NEO4J_USER", "neo4j"))
    password: str = field(default_factory=lambda: os.getenv("NEO4J_PASSWORD", ""))


@dataclass
class TracingConfig:
    """Configuration for observability/tracing."""
    enabled: bool = True
    phoenix_endpoint: str = field(default_factory=lambda: os.getenv("PHOENIX_ENDPOINT", "http://localhost:6006"))
    project_name: str = "coloraria-ingestion"


@dataclass
class RollbackConfig:
    """Configuration for rollback behavior."""
    auto_rollback_on_error: bool = True
    preserve_embeddings_cache: bool = True


@dataclass
class IngestionConfig:
    """
    Main configuration for the ingestion service.
    
    Usage:
        config = IngestionConfig.from_env()
        # or with custom values:
        config = IngestionConfig(
            embedding=EmbeddingConfig(model_name="custom-model"),
            tracing=TracingConfig(enabled=False)
        )
    """
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    neo4j: Neo4jConfig = field(default_factory=Neo4jConfig)
    tracing: TracingConfig = field(default_factory=TracingConfig)
    rollback: RollbackConfig = field(default_factory=RollbackConfig)
    
    # Cache settings
    embeddings_cache_path: str = "data/embeddings_cache.db"
    
    # Worker pool configuration (for DecoupledIngestionOrchestrator)
    cpu_workers: int = field(default_factory=lambda: int(os.getenv("INGESTION_CPU_WORKERS", "5")))
    network_workers: int = field(default_factory=lambda: int(os.getenv("INGESTION_NETWORK_WORKERS", "20")))
    disk_workers: int = field(default_factory=lambda: int(os.getenv("INGESTION_DISK_WORKERS", "2")))
    scatter_chunk_size: int = field(default_factory=lambda: int(os.getenv("INGESTION_SCATTER_CHUNK_SIZE", "500")))
    
    @classmethod
    def from_env(cls) -> "IngestionConfig":
        """Create configuration from environment variables."""
        load_dotenv()
        return cls(
            embedding=EmbeddingConfig(),
            neo4j=Neo4jConfig(),
            tracing=TracingConfig(
                enabled=os.getenv("PHOENIX_ENABLED", "true").lower() == "true"
            ),
            rollback=RollbackConfig()
        )
