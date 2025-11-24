import sys
import os
sys.path.append(os.getcwd())

from src.domain.value_objects.embedding_config import EmbeddingConfig
from src.ai.indexing.neo4j_indexer import Neo4jVectorIndexer
from src.infrastructure.graphdb.adapter import Neo4jAdapter

class MockConnection:
    def __init__(self):
        self.queries = []
        
    def execute_write(self, query, params):
        self.queries.append(query)
        print(f"Executed Query: {query.strip()}")

class MockAdapter(Neo4jAdapter):
    def __init__(self):
        self.conn = MockConnection()

def test_neo4j_index_creation():
    print("Testing Neo4j Index Creation...")
    
    config = EmbeddingConfig(
        model_name="test-model",
        dimensions=128,
        similarity="cosine"
    )
    
    adapter = MockAdapter()
    indexer = Neo4jVectorIndexer(config, adapter)
    
    indexer.create_index()
    
    # Verify query
    queries = adapter.conn.queries
    if len(queries) == 1:
        query = queries[0]
        if "CREATE VECTOR INDEX article_embeddings" in query:
            print("SUCCESS: Index creation query generated.")
        else:
            print("FAILURE: Incorrect query.")
            
        if "`vector.dimensions`: 128" in query:
            print("SUCCESS: Dimensions match config.")
        else:
            print("FAILURE: Dimensions mismatch.")
            
        if "`vector.similarity_function`: 'cosine'" in query:
            print("SUCCESS: Similarity matches config.")
        else:
            print("FAILURE: Similarity mismatch.")
    else:
        print(f"FAILURE: Expected 1 query, got {len(queries)}")

if __name__ == "__main__":
    test_neo4j_index_creation()
