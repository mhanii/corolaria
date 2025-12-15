from .base import Step, Pipeline
from .data_ingestion import DataRetriever
from .data_processing import DataProcessor
from .graph_construction import GraphConstruction
from .embedding_step import EmbeddingGenerator
from .reference_linking import LegalReferenceLinker
from src.ai.embeddings.factory import EmbeddingFactory
from src.ai.embeddings.sqlite_cache import SQLiteEmbeddingCache
from src.domain.value_objects.embedding_config import EmbeddingConfig
from src.ai.indexing.factory import IndexerFactory
from src.infrastructure.graphdb.connection import Neo4jConnection
from src.infrastructure.graphdb.adapter import Neo4jAdapter
import os
from dotenv import load_dotenv


class Doc2Graph(Pipeline):
    def __init__(self, law_id: str):
        load_dotenv()
        
        # 1. Define Configuration
        self.embedding_config = EmbeddingConfig(
            model_name="models/gemini-embedding-001",
            dimensions=768,
            similarity="cosine",
            task_type="RETRIEVAL_DOCUMENT"
        )
        
        # 2. Initialize shared Neo4j connection (used by indexer and graph construction)
        neo4j_uri = os.getenv("NEO4J_URI")
        neo4j_user = os.getenv("NEO4J_USER")
        neo4j_password = os.getenv("NEO4J_PASSWORD")
        self._connection = Neo4jConnection(neo4j_uri, neo4j_user, neo4j_password)
        self._adapter = Neo4jAdapter(self._connection)
        
        # 2b. Ensure all required indexes exist (critical for performance)
        self._adapter.ensure_constraints()
        
        # 3. Initialize Indexer and Ensure Index Exists
        self.indexer = IndexerFactory.create("neo4j", self.embedding_config, adapter=self._adapter)
        self.indexer.create_index()
        
        # 4. Create shared embedding cache
        embedding_cache = SQLiteEmbeddingCache("data/embeddings_cache.db")
        
        steps = [
            DataRetriever(name="data_retriever", search_criteria=law_id),
            DataProcessor(name="data_processor"),
            EmbeddingGenerator(
                name="embedding_generator", 
                provider=EmbeddingFactory.create(
                    provider="gemini", 
                    model=self.embedding_config.model_name,
                    dimensions=self.embedding_config.dimensions,
                    task_type=self.embedding_config.task_type,
                    cache=embedding_cache  # Pass cache to provider!
                ),
                cache=embedding_cache
            ),
            # Share adapter with GraphConstruction (single connection)
            GraphConstruction(name="graph_construction", adapter=self._adapter),
            # Extract references and create REFERS_TO relationships
            LegalReferenceLinker(name="reference_linker", adapter=self._adapter)
        ]
        super().__init__(steps)
    
    def close(self):
        """Close the shared Neo4j connection."""
        if self._connection:
            self._connection.close()
