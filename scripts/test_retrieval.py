#!/usr/bin/env python3
"""
CLI tool for testing the retrieval system.

Usage:
    python scripts/test_retrieval.py --query "freedom of speech" --strategy hybrid
    python scripts/test_retrieval.py --compare-strategies
    python scripts/test_retrieval.py --benchmark
    python scripts/test_retrieval.py --interactive
"""

import sys
import os
import argparse
from typing import List, Dict

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from dotenv import load_dotenv
from src.infrastructure.graphdb.connection import Neo4jConnection
from src.infrastructure.graphdb.adapter import Neo4jAdapter
from src.ai.embeddings.factory import EmbeddingFactory
from src.domain.value_objects.embedding_config import EmbeddingConfig
from src.domain.services.retrieval_service import RetrievalService
from src.utils.result_visualizer import ResultVisualizer

# Import strategies
from src.ai.rag.vector_search_strategy import VectorSearchStrategy
from src.ai.rag.keyword_search_strategy import KeywordSearchStrategy
from src.ai.rag.hybrid_search_strategy import HybridSearchStrategy
from src.ai.rag.graph_traversal_strategy import GraphTraversalStrategy
from src.ai.rag.llm_query_strategy import LLMQueryStrategy

# Sample test queries
SAMPLE_QUERIES = [
    "libertad de expresión",
    "derechos fundamentales",
    "Artículo 14",
    "detención preventiva",
    "igualdad ante la ley"
]


def setup_retrieval_service() -> RetrievalService:
    """Initialize the retrieval service with all strategies."""
    load_dotenv()
    
    print("Initializing retrieval service...")
    
    # Connect to Neo4j
    neo4j_uri = os.getenv("NEO4J_URI")
    neo4j_user = os.getenv("NEO4J_USER")
    neo4j_password = os.getenv("NEO4J_PASSWORD")
    
    connection = Neo4jConnection(neo4j_uri, neo4j_user, neo4j_password)
    adapter = Neo4jAdapter(connection)
    
    # Create embedding provider
    embedding_config = EmbeddingConfig(
        model_name="models/gemini-embedding-001",
        dimensions=768,
        similarity="cosine",
        task_type="RETRIEVAL_QUERY"  # Different task type for queries vs documents
    )
    
    embedding_provider = EmbeddingFactory.create(
        provider="gemini",
        model=embedding_config.model_name,
        dimensions=embedding_config.dimensions,
        task_type=embedding_config.task_type
    )
    
    # Initialize strategies
    vector_strategy = VectorSearchStrategy(adapter, embedding_provider)
    keyword_strategy = KeywordSearchStrategy(adapter)
    hybrid_strategy = HybridSearchStrategy(vector_strategy, keyword_strategy)
    graph_strategy = GraphTraversalStrategy(adapter)
    llm_strategy = LLMQueryStrategy()  # Placeholder
    
    strategies = {
        "vector": vector_strategy,
        "keyword": keyword_strategy,
        "hybrid": hybrid_strategy,
        "graph": graph_strategy,
        "llm": llm_strategy
    }
    
    service = RetrievalService(adapter, strategies)
    
    print(f"✓ Initialized with strategies: {list(strategies.keys())}\n")
    
    return service


def run_single_query(service: RetrievalService, query: str, strategy: str, top_k: int):
    """Run a single query and display results."""
    print(f"Searching for: '{query}' using {strategy} strategy")
    print(f"Top K: {top_k}\n")
    
    results = service.search(query, strategy=strategy, top_k=top_k)
    
    ResultVisualizer.print_results(results, max_preview=200, use_color=True)


def compare_strategies(service: RetrievalService, query: str, top_k: int):
    """Compare all strategies on a single query."""
    print(f"\nComparing strategies for query: '{query}'\n")
    
    strategies = ["vector", "keyword", "hybrid"]
    multi_results = service.multi_strategy_search(query, strategies=strategies, top_k=top_k)
    
    ResultVisualizer.compare_strategies(multi_results, top_k=top_k, use_color=True)


def run_benchmark(service: RetrievalService, queries: List[str], top_k: int):
    """Benchmark all strategies on multiple queries."""
    print(f"\nRunning benchmark on {len(queries)} queries...\n")
    
    strategies = ["vector", "keyword", "hybrid"]
    benchmark_results = service.benchmark_strategies(queries, strategies=strategies, top_k=top_k)
    
    ResultVisualizer.print_benchmark(benchmark_results, use_color=True)


def interactive_mode(service: RetrievalService):
    """Interactive query mode."""
    print("\n" + "="*80)
    print("Interactive Retrieval Testing Mode")
    print("="*80)
    print("\nCommands:")
    print("  search <query>          - Search with hybrid strategy")
    print("  vector <query>          - Search with vector strategy")
    print("  keyword <query>         - Search with keyword strategy")
    print("  compare <query>         - Compare all strategies")
    print("  benchmark               - Run benchmark on sample queries")
    print("  help                    - Show this help")
    print("  quit                    - Exit interactive mode")
    print()
    
    while True:
        try:
            user_input = input("\n> ").strip()
            
            if not user_input:
                continue
            
            parts = user_input.split(maxsplit=1)
            command = parts[0].lower()
            query = parts[1] if len(parts) > 1 else ""
            
            if command == "quit":
                print("Exiting...")
                break
            
            elif command == "help":
                print("\nCommands:")
                print("  search <query>          - Search with hybrid strategy")
                print("  vector <query>          - Search with vector strategy")
                print("  keyword <query>         - Search with keyword strategy")
                print("  compare <query>         - Compare all strategies")
                print("  benchmark               - Run benchmark on sample queries")
                print("  help                    - Show this help")
                print("  quit                    - Exit interactive mode")
            
            elif command == "search":
                if not query:
                    print("Error: Please provide a query")
                    continue
                run_single_query(service, query, "hybrid", top_k=10)
            
            elif command == "vector":
                if not query:
                    print("Error: Please provide a query")
                    continue
                run_single_query(service, query, "vector", top_k=10)
            
            elif command == "keyword":
                if not query:
                    print("Error: Please provide a query")
                    continue
                run_single_query(service, query, "keyword", top_k=10)
            
            elif command == "compare":
                if not query:
                    print("Error: Please provide a query")
                    continue
                compare_strategies(service, query, top_k=5)
            
            elif command == "benchmark":
                run_benchmark(service, SAMPLE_QUERIES, top_k=5)
            
            else:
                print(f"Unknown command: {command}. Type 'help' for available commands.")
        
        except KeyboardInterrupt:
            print("\n\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")


def main():
    parser = argparse.ArgumentParser(description="Test the retrieval system")
    
    parser.add_argument("--query", "-q", type=str, help="Search query")
    parser.add_argument("--strategy", "-s", type=str, default="hybrid",
                       choices=["vector", "keyword", "hybrid", "graph", "llm"],
                       help="Retrieval strategy to use")
    parser.add_argument("--top-k", "-k", type=int, default=10,
                       help="Number of results to return")
    parser.add_argument("--compare-strategies", action="store_true",
                       help="Compare multiple strategies")
    parser.add_argument("--benchmark", action="store_true",
                       help="Run benchmark on sample queries")
    parser.add_argument("--interactive", "-i", action="store_true",
                       help="Enter interactive mode")
    parser.add_argument("--export", type=str,
                       help="Export results to file (JSON or TXT)")
    
    args = parser.parse_args()
    
    # Initialize service
    service = setup_retrieval_service()
    
    # Interactive mode
    if args.interactive:
        interactive_mode(service)
        return
    
    # Benchmark mode
    if args.benchmark:
        run_benchmark(service, SAMPLE_QUERIES, args.top_k)
        return
    
    # Compare strategies mode
    if args.compare_strategies:
        if not args.query:
            print("Error: --query required for comparison mode")
            parser.print_help()
            return
        compare_strategies(service, args.query, args.top_k)
        return
    
    # Single query mode
    if args.query:
        results = service.search(args.query, strategy=args.strategy, top_k=args.top_k)
        
        ResultVisualizer.print_results(results, max_preview=200, use_color=True)
        
        # Export if requested
        if args.export:
            format_ext = args.export.split('.')[-1]
            ResultVisualizer.export_results(results, args.export, format=format_ext)
        
        return
    
    # No arguments - show help
    parser.print_help()
    print("\nTip: Use --interactive (-i) for interactive testing mode")


if __name__ == "__main__":
    main()
