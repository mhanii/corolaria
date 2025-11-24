import sys
import os
from unittest.mock import MagicMock
sys.path.append(os.getcwd())

# Mock google.genai before importing provider
mock_genai = MagicMock()
sys.modules["google.genai"] = mock_genai
sys.modules["google"] = MagicMock()
sys.modules["google"].genai = mock_genai

from src.ai.embeddings.gemini_provider import GeminiEmbeddingProvider

def test_gemini_provider():
    print("Testing GeminiEmbeddingProvider...")
    
    # Setup Mock
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    
    # Mock response
    mock_embedding = MagicMock()
    mock_embedding.values = [0.1] * 768
    mock_response = MagicMock()
    mock_response.embeddings = [mock_embedding]
    mock_client.models.embed_content.return_value = mock_response
    
    # Initialize Provider
    provider = GeminiEmbeddingProvider(
        model="models/gemini-embedding-001", 
        dimensions=768, 
        task_type="RETRIEVAL_DOCUMENT"
    )
    
    # Test get_embedding
    print("Testing get_embedding...")
    text = "Test content"
    embedding = provider.get_embedding(text)
    
    # Verify call
    mock_client.models.embed_content.assert_called()
    call_args = mock_client.models.embed_content.call_args
    
    if call_args.kwargs['model'] == "models/gemini-embedding-001":
        print("SUCCESS: Model matches.")
    else:
        print(f"FAILURE: Model mismatch. Got {call_args.kwargs['model']}")
        
    # Verify EmbedContentConfig was called correctly
    mock_genai.types.EmbedContentConfig.assert_called_with(
        task_type="RETRIEVAL_DOCUMENT",
        output_dimensionality=768
    )
    print("SUCCESS: EmbedContentConfig called with correct task_type and dimensions.")

    if len(embedding) == 768:
        print("SUCCESS: Embedding returned.")
    else:
        print("FAILURE: Embedding length incorrect.")

if __name__ == "__main__":
    test_gemini_provider()
