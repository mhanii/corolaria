from .base import Step, Pipeline
from .data_ingestion import DataRetriever
from .data_processing import DataProcessor
from .graph_construction import GraphConstruction
from .embedding_step import EmbeddingGenerator
from src.ai.embeddings.factory import EmbeddingFactory
from src.ai.embeddings.json_cache import JSONFileCache
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
        # This should ideally come from a config file or env vars
        self.embedding_config = EmbeddingConfig(
            model_name="models/gemini-embedding-001",
            dimensions=768,
            similarity="cosine",
            task_type="RETRIEVAL_DOCUMENT"
        )
        
        # 2. Initialize Infrastructure for Indexing (needed for Neo4j Indexer)
        neo4j_uri = os.getenv("NEO4J_URI")
        neo4j_user = os.getenv("NEO4J_USER")
        neo4j_password = os.getenv("NEO4J_PASSWORD")
        connection = Neo4jConnection(neo4j_uri, neo4j_user, neo4j_password)
        adapter = Neo4jAdapter(connection)
        
        # 3. Initialize Indexer and Ensure Index Exists
        # Change "neo4j" to "qdrant" to switch backends
        self.indexer = IndexerFactory.create("neo4j", self.embedding_config, adapter=adapter)
        self.indexer.create_index()
        
        steps = [
            DataRetriever(name="data_retriever", search_criteria=law_id),
            DataProcessor(name="data_processor"),
            EmbeddingGenerator(
                name="embedding_generator", 
                provider=EmbeddingFactory.create(
                    provider="gemini", 
                    model=self.embedding_config.model_name,
                    dimensions=self.embedding_config.dimensions,
                    task_type=self.embedding_config.task_type
                ),
                cache=JSONFileCache("data/embeddings_cache.json")
            ),
            GraphConstruction(name="graph_contructrion")
            # Additional steps can be added here
        ]
        super().__init__(steps)
        
        # Close connection created for indexer setup (GraphConstruction creates its own)
        connection.close()




