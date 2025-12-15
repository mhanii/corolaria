"""
Resource Manager Service.

Handles initialization and lifecycle of shared resources:
- Neo4j Connection and Adapter
- Embedding Cache (SQLite)
- Embedding Provider (Gemini/HF)
- Vector Indexer
"""
from typing import Optional, Any
from src.ingestion.config import IngestionConfig
from src.domain.value_objects.embedding_config import EmbeddingConfig
from src.infrastructure.graphdb.connection import Neo4jConnection
from src.infrastructure.graphdb.adapter import Neo4jAdapter
from src.ai.embeddings.factory import EmbeddingFactory
from src.ai.embeddings.sqlite_cache import SQLiteEmbeddingCache
from src.ai.indexing.factory import IndexerFactory


class ResourceManager:
    def __init__(self, config: IngestionConfig, simulate_embeddings: bool = False, use_cache: bool = True):
        self.config = config
        self.simulate_embeddings = simulate_embeddings
        self.use_cache = use_cache
        # Resources
        self.connection: Optional[Neo4jConnection] = None
        self.adapter: Optional[Neo4jAdapter] = None
        self.embedding_cache: Optional[SQLiteEmbeddingCache] = None
        self.embedding_provider: Any = None
        self.indexer: Any = None
        # Embedding Config
        self.embedding_config = EmbeddingConfig(
            model_name="models/gemini-embedding-001",
            dimensions=768,
            similarity="cosine",
            task_type="RETRIEVAL_DOCUMENT"
        )

    async def initialize(self):
        """Initialize all shared resources."""
        from src.utils.logger import step_logger
        
        # 1. Neo4j
        self.connection = Neo4jConnection(
            self.config.neo4j.uri,
            self.config.neo4j.user,
            self.config.neo4j.password
        )
        self.adapter = Neo4jAdapter(self.connection)
        self.adapter.ensure_constraints()
        
        # 2. Embedding Cache (conditional)
        if self.use_cache:
            self.embedding_cache = SQLiteEmbeddingCache("data/embeddings_cache.db")
            step_logger.info("[ResourceManager] Embedding cache: ENABLED (SQLite)")
        else:
            self.embedding_cache = None
            step_logger.info("[ResourceManager] Embedding cache: DISABLED (--clean mode)")
        
        # 3. Embedding Provider
        self.embedding_provider = EmbeddingFactory.create(
            provider="gemini",
            model=self.embedding_config.model_name,
            dimensions=self.embedding_config.dimensions,
            task_type=self.embedding_config.task_type,
            simulate=self.simulate_embeddings,
            cache=self.embedding_cache
        )
        
        # 4. Indexer
        self.indexer = IndexerFactory.create(
            "neo4j",
            self.embedding_config,
            adapter=self.adapter
        )

    def close(self):
        """Release resources."""
        if self.connection:
            self.connection.close()

    def prepare_database(self):
        """Run initial database preparation (Stage 0)."""
        if self.indexer:
            self.indexer.drop_index()
            
    def create_vector_index(self):
        """Create vector index (Stage 3)."""
        if self.indexer:
            self.indexer.create_index()
