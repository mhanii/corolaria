from typing import Optional
from src.domain.value_objects.embedding_config import EmbeddingConfig
from src.domain.interfaces.vector_indexer import VectorIndexer
from src.ai.indexing.neo4j_indexer import Neo4jVectorIndexer
from src.ai.indexing.qdrant_indexer import QdrantVectorIndexer
from src.domain.interfaces.graph_adapter import GraphAdapter

class IndexerFactory:
    @staticmethod
    def create(
        indexer_type: str, 
        config: EmbeddingConfig, 
        adapter: Optional[GraphAdapter] = None,
        **kwargs
    ) -> VectorIndexer:
        
        if indexer_type.lower() == "neo4j":
            if not adapter:
                raise ValueError("GraphAdapter is required for Neo4jVectorIndexer")
            return Neo4jVectorIndexer(config, adapter)
            
        elif indexer_type.lower() == "qdrant":
            return QdrantVectorIndexer(config, **kwargs)
            
        else:
            raise ValueError(f"Unknown indexer type: {indexer_type}")
