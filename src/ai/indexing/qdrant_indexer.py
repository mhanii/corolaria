from typing import List, Any, Dict
import os
from src.domain.interfaces.vector_indexer import VectorIndexer
from src.domain.value_objects.embedding_config import EmbeddingConfig
from src.utils.logger import step_logger

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct
except ImportError:
    QdrantClient = None

class QdrantVectorIndexer(VectorIndexer):
    """
    Vector Indexer for Qdrant.
    """
    
    def __init__(self, config: EmbeddingConfig, collection_name: str = "articles"):
        super().__init__(config)
        if QdrantClient is None:
            raise ImportError("qdrant-client is not installed.")
            
        self.collection_name = collection_name
        
        # Initialize client (env vars or default to local/memory)
        qdrant_url = os.getenv("QDRANT_URL", ":memory:") # Default to in-memory for dev if not set
        qdrant_api_key = os.getenv("QDRANT_API_KEY")
        
        self.client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)

    def create_index(self):
        """
        Create Qdrant collection.
        """
        similarity_map = {
            "cosine": Distance.COSINE,
            "euclidean": Distance.EUCLID,
            "dot": Distance.DOT
        }
        dist = similarity_map.get(self.config.similarity, Distance.COSINE)
        
        try:
            # Check if exists
            if not self.client.collection_exists(self.collection_name):
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=self.config.dimensions, distance=dist)
                )
                step_logger.info(f"Created Qdrant collection '{self.collection_name}' (dim={self.config.dimensions}).")
            else:
                step_logger.info(f"Qdrant collection '{self.collection_name}' already exists.")
        except Exception as e:
            step_logger.error(f"Failed to create Qdrant collection: {e}")

    def upsert(self, items: List[Dict[str, Any]]):
        """
        Upsert vectors to Qdrant.
        Expected items format: {"id": str/int, "vector": list, "payload": dict}
        """
        if not items:
            return

        points = []
        for item in items:
            # Qdrant requires integer or UUID strings. 
            # If our IDs are arbitrary strings (e.g. "BOE-A-2025-1"), we might need to hash them to UUIDs or use them if they are UUIDs.
            # For simplicity, let's assume we might need to hash them if they aren't valid UUIDs/ints.
            # But let's try passing as is first (Qdrant supports string UUIDs).
            
            points.append(PointStruct(
                id=item["id"], # Must be int or UUID
                vector=item["vector"],
                payload=item.get("payload", {})
            ))
            
        try:
            self.client.upsert(
                collection_name=self.collection_name,
                points=points
            )
            step_logger.info(f"Upserted {len(points)} vectors to Qdrant.")
        except Exception as e:
            step_logger.error(f"Failed to upsert to Qdrant: {e}")
