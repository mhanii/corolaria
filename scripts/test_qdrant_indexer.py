import sys
import os
sys.path.append(os.getcwd())

from src.domain.value_objects.embedding_config import EmbeddingConfig
from src.ai.indexing.qdrant_indexer import QdrantVectorIndexer
from unittest.mock import MagicMock

# Mock QdrantClient before importing the indexer if possible, 
# but since we import it inside the module, we can mock the class in the module.
import src.ai.indexing.qdrant_indexer as qdrant_module

# Mock the QdrantClient class
MockClient = MagicMock()
qdrant_module.QdrantClient = MagicMock(return_value=MockClient)
# Mock Distance enum
class MockDistance:
    COSINE = "Cosine"
class MockDistance:
    COSINE = "Cosine"
    EUCLID = "Euclid"
    DOT = "Dot"
qdrant_module.Distance = MockDistance
qdrant_module.VectorParams = MagicMock()
qdrant_module.PointStruct = MagicMock()

def test_qdrant_indexing():
    print("Testing Qdrant Indexing...")
    
    config = EmbeddingConfig(
        model_name="test-model",
        dimensions=128,
        similarity="cosine"
    )
    
    indexer = QdrantVectorIndexer(config, collection_name="test_collection")
    
    # 1. Test Create Index
    print("Testing create_index...")
    MockClient.collection_exists.return_value = False
    indexer.create_index()
    
    MockClient.create_collection.assert_called_once()
    call_args = MockClient.create_collection.call_args
    if call_args.kwargs['collection_name'] == "test_collection":
        print("SUCCESS: Collection name matches.")
    else:
        print("FAILURE: Collection name mismatch.")
        
    # 2. Test Upsert
    print("Testing upsert...")
    items = [
        {"id": 1, "vector": [0.1]*128, "payload": {"test": "data"}}
    ]
    indexer.upsert(items)
    
    MockClient.upsert.assert_called_once()
    upsert_args = MockClient.upsert.call_args
    if upsert_args.kwargs['collection_name'] == "test_collection":
        print("SUCCESS: Upsert collection name matches.")
    else:
        print("FAILURE: Upsert collection name mismatch.")
        
    qdrant_module.PointStruct.assert_called_with(
        id=1,
        vector=[0.1]*128,
        payload={"test": "data"}
    )
    print("SUCCESS: PointStruct called with correct ID and data.")

if __name__ == "__main__":
    test_qdrant_indexing()
