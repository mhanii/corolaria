from typing import List, Any, Dict
from src.domain.interfaces.vector_indexer import VectorIndexer
from src.domain.value_objects.embedding_config import EmbeddingConfig
from src.domain.interfaces.graph_adapter import GraphAdapter
from src.utils.logger import step_logger

class Neo4jVectorIndexer(VectorIndexer):
    """
    Vector Indexer for Neo4j.
    Manages the creation of the vector index.
    Upsert is handled implicitly by the GraphConstruction step (saving properties),
    so upsert() here is a no-op or could be used for explicit updates if needed.
    """
    
    def __init__(self, config: EmbeddingConfig, adapter: GraphAdapter):
        super().__init__(config)
        self.adapter = adapter

    def create_index(self):
        """
        Create the vector index in Neo4j.
        """
        # Map config similarity to Neo4j similarity function
        similarity_map = {
            "cosine": "cosine",
            "euclidean": "euclidean",
            "dot": "dotproduct" # Neo4j uses 'dotproduct'
        }
        
        sim_func = similarity_map.get(self.config.similarity, "cosine")
        
        try:
            self.adapter.create_vector_index(
                index_name="article_embeddings",
                label="Article",
                property_name="embedding",
                dimensions=self.config.dimensions,
                similarity_function=sim_func
            )
            step_logger.info(f"Ensured Neo4j vector index 'article_embeddings' exists (dim={self.config.dimensions}, sim={sim_func}).")
        except Exception as e:
            step_logger.error(f"Failed to create Neo4j vector index: {e}")

    def upsert(self, items: List[Dict[str, Any]]):
        """
        No-op for Neo4j in this architecture.
        Vectors are saved as properties on the nodes during GraphConstruction.
        """
        pass
