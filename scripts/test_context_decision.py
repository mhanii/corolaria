#!/usr/bin/env python3
"""
Test script for context decision and follow-up detection.
Tests the logic that determines when to skip RAG and reuse previous context.
"""
import os
import sys
from pathlib import Path

# Add project root to path
project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

# Load .env file FIRST before checking env vars
from dotenv import load_dotenv
load_dotenv(Path(project_root) / ".env")

# Set default env vars (only if not already set by .env)
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USER", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "password")


def test_context_decision_heuristics():
    """Test heuristic-based decision logic without embeddings."""
    print("\n=== Testing Context Decision Heuristics ===\n")
    
    from src.ai.context_decision import ContextDecision, LEGAL_KEYWORDS
    from src.domain.models.conversation import Conversation
    
    decision = ContextDecision()
    
    # Create mock conversation with previous context
    conv = Conversation()
    conv.add_user_message("¿Qué dice el artículo 14?")
    conv.add_assistant_message("El artículo 14 establece la igualdad [1].")
    previous_context = '[{"article_id": "1", "text": "Artículo 14..."}]'
    
    # Test 1: Long query should need collector
    result = decision.needs_context_collector(
        "¿Puedes explicarme en detalle qué significa el derecho a la igualdad ante la ley?",
        conv, 
        previous_context
    )
    print(f"1. Long query (12 words): needs_collector={result.needs_collector}, reason={result.reason}")
    assert result.needs_collector, "Long queries should need collector"
    
    # Test 2: Query with legal keywords should need collector
    result = decision.needs_context_collector(
        "¿Y el artículo 15?",
        conv,
        previous_context
    )
    print(f"2. Legal keyword query: needs_collector={result.needs_collector}, reason={result.reason}")
    assert result.needs_collector, "Legal keyword queries should need collector"
    
    # Test 3: Simple clarification should skip collector
    result = decision.needs_context_collector(
        "¿Estás seguro?",
        conv,
        previous_context
    )
    print(f"3. Clarification '¿Estás seguro?': needs_collector={result.needs_collector}, reason={result.reason}")
    assert not result.needs_collector, "Simple clarifications should skip collector"
    
    # Test 4: Simple clarification without previous context should need collector
    result = decision.needs_context_collector(
        "¿Estás seguro?",
        conv,
        None  # No previous context
    )
    print(f"4. Clarification w/o context: needs_collector={result.needs_collector}, reason={result.reason}")
    assert result.needs_collector, "Should need collector without previous context"
    
    # Test 5: Other clarification patterns
    patterns = ["¿seguro?", "¿por qué?", "¿cómo?", "ok", "vale", "entiendo"]
    for pattern in patterns:
        result = decision.needs_context_collector(pattern, conv, previous_context)
        print(f"5. Pattern '{pattern}': needs_collector={result.needs_collector}")
        if result.needs_collector:
            print(f"   Reason: {result.reason}")
    
    print("\n✅ Heuristic tests completed!")
    return True


def test_chroma_store():
    """Test ChromaDB store for classification embeddings."""
    print("\n=== Testing ChromaDB Store ===\n")
    
    from src.infrastructure.chroma import ChromaClassificationStore
    
    # Use temp directory for test
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ChromaClassificationStore(persist_directory=tmpdir)
        
        print(f"1. Store initialized: {store.count()} embeddings")
        assert store.count() == 0, "Should start empty"
        
        # Without embedding provider, can't seed yet
        print("2. Cannot seed without embedding provider (expected)")
        count = store.seed_defaults()
        assert count == 0, "Should not seed without provider"
        
        print("\n✅ ChromaDB store basic tests passed!")
        return True


def test_chroma_with_embeddings():
    """Test ChromaDB with real embeddings (requires API key)."""
    print("\n=== Testing ChromaDB with Embeddings ===\n")
    
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("⚠️ Skipping embedding tests (no GOOGLE_API_KEY)")
        return True
    
    from src.infrastructure.chroma import ChromaClassificationStore
    from src.ai.embeddings.gemini_provider import GeminiEmbeddingProvider
    
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize with embedding provider
        provider = GeminiEmbeddingProvider()
        store = ChromaClassificationStore(persist_directory=tmpdir, embedding_provider=provider)
        
        # Seed with defaults
        print("1. Seeding default phrases...")
        count = store.seed_defaults()
        print(f"   Seeded {count} phrases")
        assert count > 0, "Should seed some phrases"
        
        # Test similarity search
        print("2. Testing similarity search...")
        matches = store.find_similar("¿estás seguro de eso?", top_k=3)
        print(f"   Found {len(matches)} matches:")
        for m in matches:
            print(f"   - '{m['phrase']}' (similarity: {m['similarity']:.3f})")
        
        assert len(matches) > 0, "Should find similar phrases"
        
        # Test with non-matching query
        print("3. Testing with unrelated query...")
        matches = store.find_similar("¿Cuál es la población de España?", top_k=3)
        print(f"   Found {len(matches)} matches, best similarity: {matches[0]['similarity']:.3f}")
        
        print("\n✅ ChromaDB embedding tests passed!")
        return True


def test_context_decision_with_embeddings():
    """Test full context decision with embedding similarity."""
    print("\n=== Testing Context Decision with Embeddings ===\n")
    
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("⚠️ Skipping (no GOOGLE_API_KEY)")
        return True
    
    from src.ai.context_decision import ContextDecision
    from src.infrastructure.chroma import ChromaClassificationStore
    from src.ai.embeddings.gemini_provider import GeminiEmbeddingProvider
    from src.domain.models.conversation import Conversation
    
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup
        provider = GeminiEmbeddingProvider()
        store = ChromaClassificationStore(persist_directory=tmpdir, embedding_provider=provider)
        store.seed_defaults()
        
        decision = ContextDecision(chroma_store=store)
        
        conv = Conversation()
        conv.add_user_message("¿Qué dice el artículo 14?")
        conv.add_assistant_message("El artículo 14 establece la igualdad [1].")
        previous_context = '[{"article_id": "1", "text": "Artículo 14..."}]'
        
        # Test similar to clarification but not exact pattern
        result = decision.needs_context_collector(
            "¿eso es correcto?",  # Similar meaning but not in patterns
            conv,
            previous_context
        )
        print(f"1. '¿eso es correcto?': needs_collector={result.needs_collector}")
        print(f"   Reason: {result.reason}, similarity: {result.similarity_score}")
        
        print("\n✅ Full context decision tests passed!")
        return True


if __name__ == "__main__":
    all_passed = True
    
    try:
        all_passed &= test_context_decision_heuristics()
    except Exception as e:
        print(f"\n❌ Heuristic tests failed: {e}")
        all_passed = False
    
    try:
        all_passed &= test_chroma_store()
    except Exception as e:
        print(f"\n❌ ChromaDB tests failed: {e}")
        all_passed = False
    
    try:
        all_passed &= test_chroma_with_embeddings()
    except Exception as e:
        print(f"\n❌ Embedding tests failed: {e}")
        all_passed = False
    
    try:
        all_passed &= test_context_decision_with_embeddings()
    except Exception as e:
        print(f"\n❌ Full decision tests failed: {e}")
        all_passed = False
    
    if all_passed:
        print("\n" + "=" * 50)
        print("✅ All tests passed!")
        print("=" * 50)
        sys.exit(0)
    else:
        print("\n" + "=" * 50)
        print("❌ Some tests failed!")
        print("=" * 50)
        sys.exit(1)
