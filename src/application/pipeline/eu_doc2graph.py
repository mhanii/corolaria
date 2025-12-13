"""
EU Document to Graph pipeline.

Complete pipeline for ingesting EU legal documents from EUR-Lex
into Neo4j graph database with embeddings.

Usage:
    pipeline = EUDoc2Graph("12016P/TXT")  # Charter of Fundamental Rights
    result = pipeline.run(None)
"""
from src.application.pipeline.base import Step, Pipeline
from src.application.pipeline.eu_data_retriever import EUDataRetriever
from src.application.pipeline.eu_html_processor import EUHTMLProcessor
from src.application.pipeline.eu_graph_construction import EUGraphConstruction
from src.application.pipeline.embedding_step import EmbeddingGenerator
from src.ai.embeddings.factory import EmbeddingFactory
from src.ai.embeddings.sqlite_cache import SQLiteEmbeddingCache
from src.domain.value_objects.embedding_config import EmbeddingConfig
from src.ai.indexing.factory import IndexerFactory
from src.infrastructure.graphdb.connection import Neo4jConnection
from src.infrastructure.graphdb.adapter import Neo4jAdapter
import os
from dotenv import load_dotenv
from src.utils.logger import step_logger


class EUDoc2Graph(Pipeline):
    """
    Pipeline for ingesting EU documents from EUR-Lex into Neo4j.
    
    Steps:
    1. EUDataRetriever - Fetch HTML from EUR-Lex public endpoint
    2. EUHTMLProcessor - Parse HTML into EUNormativa domain model
    3. EmbeddingGenerator - Generate embeddings for all articles
    4. EUGraphConstruction - Persist to Neo4j graph
    
    Example:
        >>> pipeline = EUDoc2Graph("32016R0679")  # GDPR
        >>> result = pipeline.run(None)
    """
    
    def __init__(self, celex: str, language: str = "ES"):
        """
        Initialize EU ingestion pipeline.
        
        Args:
            celex: CELEX number (e.g., "32016R0679" for GDPR)
            language: 2-letter language code (ES, EN, FR, etc.)
        """
        load_dotenv()
        
        self.celex = celex
        self.language = language
        
        # 1. Define embedding configuration
        self.embedding_config = EmbeddingConfig(
            model_name="models/gemini-embedding-001",
            dimensions=768,
            similarity="cosine",
            task_type="RETRIEVAL_DOCUMENT"
        )
        
        # 2. Initialize shared Neo4j connection
        neo4j_uri = os.getenv("NEO4J_URI")
        neo4j_user = os.getenv("NEO4J_USER")
        neo4j_password = os.getenv("NEO4J_PASSWORD")
        self._connection = Neo4jConnection(neo4j_uri, neo4j_user, neo4j_password)
        self._adapter = Neo4jAdapter(self._connection)
        
        # 2b. Ensure indexes exist
        self._adapter.ensure_constraints()
        
        # 3. Initialize indexer
        self.indexer = IndexerFactory.create("neo4j", self.embedding_config, adapter=self._adapter)
        self.indexer.create_index()
        
        # 4. Build pipeline steps
        steps = [
            # Step 1: Fetch HTML from EUR-Lex
            EUDataRetriever(
                name="eu_data_retriever",
                celex=celex,
                language=language
            ),
            
            # Step 2: Parse HTML into EUNormativa
            EUHTMLProcessor(name="eu_html_processor"),
            
            # Step 3: Generate embeddings for articles
            EmbeddingGenerator(
                name="embedding_generator",
                provider=EmbeddingFactory.create(
                    provider="gemini",
                    model=self.embedding_config.model_name,
                    dimensions=self.embedding_config.dimensions,
                    task_type=self.embedding_config.task_type
                ),
                cache=SQLiteEmbeddingCache("data/embeddings_cache.db")
            ),
            
            # Step 4: Persist to Neo4j
            EUGraphConstruction(
                name="eu_graph_construction",
                adapter=self._adapter
            ),
        ]
        
        super().__init__(steps)
        
        step_logger.info(f"[EUDoc2Graph] Initialized for {celex} ({language})")
    
    def close(self):
        """Close the shared Neo4j connection."""
        if self._connection:
            self._connection.close()
