"""
Test the REAL AgentCollector with configurable provider.
Uses actual Neo4j and embeddings to test the full agent workflow.
"""
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

# Load environment variables
from dotenv import load_dotenv
load_dotenv()


def test_real_agent_collector(provider: str = "azure_openai"):
    """Test the real AgentCollector with specified provider."""
    print("=" * 60)
    print(f"Testing REAL AgentCollector with provider: {provider}")
    print("=" * 60)
    
    # Import dependencies
    from src.api.v1.dependencies import get_neo4j_adapter, get_embedding_provider
    from src.ai.context_collectors import AgentCollector
    
    # Initialize using dependency functions
    print("Initializing Neo4j adapter...")
    neo4j = get_neo4j_adapter()
    
    # Initialize embedding provider
    print("Initializing embedding provider...")
    embedding_provider = get_embedding_provider()
    
    # Create AgentCollector with specified provider
    print(f"Creating AgentCollector with provider={provider}...")
    
    # Select model based on provider
    if provider == "azure_openai":
        model_name = "gpt-5-mini"
    elif provider == "openai":
        model_name = "gpt-4o"
    else:
        model_name = "gemini-2.0-flash"
    
    agent = AgentCollector(
        graph_adapter=neo4j,
        embedding_provider=embedding_provider,
        provider=provider,
        model_name=model_name,
        temperature=1 if provider in ["azure_openai", "openai"] else 0.3,  # o1 models need temp=1
        max_iterations=5
    )
    
    print(f"Agent initialized: {agent.name}")
    print(f"Provider: {agent._provider}")
    print(f"Model: {agent._model_name}")
    print()
    
    # Test query
    query = "¿Cuáles son los requisitos para el matrimonio civil en España?"
    print(f"Query: {query}")
    print("-" * 40)
    
    # Collect context
    print("Running agent collection...")
    result = agent.collect(query, top_k=5)
    
    print(f"\nResults:")
    print(f"  Strategy: {result.strategy_name}")
    print(f"  Chunks collected: {len(result.chunks)}")
    print(f"  Metadata: {result.metadata}")
    
    if result.chunks:
        print(f"\nFirst chunk preview:")
        chunk = result.chunks[0]
        text = chunk.get("article_text", chunk.get("full_text", ""))[:200]
        print(f"  Article: {chunk.get('article_id', 'unknown')}")
        print(f"  Text: {text}...")
    
    print("\n" + "=" * 60)
    print("AGENT TEST COMPLETED!")
    print("=" * 60)
    
    return result


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="azure_openai", 
                        choices=["gemini", "openai", "azure_openai"],
                        help="LLM provider to use")
    args = parser.parse_args()
    
    try:
        result = test_real_agent_collector(args.provider)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
