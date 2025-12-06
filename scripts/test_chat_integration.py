"""
Integration tests for Chat API.
Uses FastAPI TestClient to verify endpoints without running a separate server process.
Mocks dependencies to avoid external connections (Neo4j, LLM APIs).
"""
import os
import sys
from pathlib import Path

# Add project root to python path to handle imports correctly
project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

# Set dummy env vars before imports
os.environ["GOOGLE_API_KEY"] = "fake-key"
os.environ["NEO4J_URI"] = "bolt://localhost:7687"
os.environ["NEO4J_USER"] = "neo4j"
os.environ["NEO4J_PASSWORD"] = "password"

from unittest.mock import MagicMock, AsyncMock
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.v1.dependencies import get_chat_service, get_conversation_service
from src.domain.services.chat_service import ChatService
from src.domain.services.conversation_service import ConversationService
from src.domain.interfaces.llm_provider import LLMResponse

# 1. Setup Data
MOCK_CONVERSATION_ID = "mock-conv-id"

# 2. Define Dependency Overrides
# 3. Create Shared Singleton for Test
shared_conversation_service = ConversationService()
# Pre-seed a conversation
mock_conv = shared_conversation_service.create_conversation()
# Update ID in the service dict properly
del shared_conversation_service._conversations[mock_conv.id]
mock_conv.id = MOCK_CONVERSATION_ID
shared_conversation_service._conversations[MOCK_CONVERSATION_ID] = mock_conv
mock_conv.add_user_message("Hello")

def override_get_chat_service():
    """Returns a ChatService with mocked internal components."""
    
    # Mock LLM Provider
    mock_llm = MagicMock()
    mock_llm.model = "gemini-mock"
    # Use AsyncMock for agenerate
    mock_llm.agenerate = AsyncMock(return_value=LLMResponse(
        content="Human dignity is inviolable [1].",
        model="gemini-mock",
        usage={"total_tokens": 50}
    ))
    
    # Mock Neo4j Adapter
    mock_adapter = MagicMock()
    mock_adapter.vector_search.return_value = [
        {
            "article_id": "1",
            "article_number": "Art 10",
            "article_text": "Dignity is fundamental.",
            "normativa_title": "Constitution",
            "article_path": "Title I",
            "score": 0.95,
            "metadata": {}
        }
    ]
    
    # Mock Embedding Provider
    mock_embedding = MagicMock()
    mock_embedding.get_embedding.return_value = [0.1] * 768
    
    # Import dependencies required for ChatService constructor
    from src.ai.citations.citation_engine import CitationEngine
    from src.ai.prompts.prompt_builder import PromptBuilder
    
    # Create the service with mocks AND shared conversation service
    service = ChatService(
        llm_provider=mock_llm,
        neo4j_adapter=mock_adapter,
        embedding_provider=mock_embedding,
        conversation_service=shared_conversation_service,
        citation_engine=CitationEngine(),
        prompt_builder=PromptBuilder(),
        retrieval_top_k=3
    )
    return service

def override_get_conversation_service():
    """Returns the shared conversation service."""
    return shared_conversation_service

# Apply overrides
app.dependency_overrides[get_chat_service] = override_get_chat_service
app.dependency_overrides[get_conversation_service] = override_get_conversation_service

client = TestClient(app)

def test_chat_flow():
    print("\n--- Testing POST /api/v1/chat ---")
    payload = {
        "message": "What about dignity?",
        "top_k": 3
    }
    
    response = client.post("/api/v1/chat", json=payload)
    
    # Validation
    print(f"Status: {response.status_code}")
    if response.status_code != 200:
        print(f"Error: {response.json()}")
        exit(1)
        
    data = response.json()
    print(f"Response: {data['response']}")
    print(f"Citations: {len(data['citations'])}")
    
    # Assertions
    assert response.status_code == 200
    assert "dignity" in data["response"].lower()
    assert len(data["citations"]) == 1
    assert data["citations"][0]["index"] == 1
    
    return data["conversation_id"]

def test_history_flow(conv_id):
    print(f"\n--- Testing GET /api/v1/chat/{conv_id} ---")
    response = client.get(f"/api/v1/chat/{conv_id}")
    
    print(f"Status: {response.status_code}")
    if response.status_code != 200:
        print(f"Error: {response.json()}")
    
    assert response.status_code == 200
    data = response.json()
    print(f"Messages found: {len(data['messages'])}")
    assert len(data['messages']) >= 2 # User + Assistant

if __name__ == "__main__":
    try:
        cid = test_chat_flow()
        # Test history with the ID returned from chat (which uses the mocked conv service)
        test_history_flow(cid)
        
        # Also test the pre-seeded conversation
        test_history_flow(MOCK_CONVERSATION_ID)
        
        print("\n✅ All integration tests passed!")
    except Exception as e:
        print(f"\n❌ Tests failed: {e}")
        exit(1)
