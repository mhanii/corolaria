from typing import List, Dict, Optional, Any
import time
from src.domain.interfaces.retrieval_strategy import RetrievalStrategy
from src.domain.value_objects.search_result import SearchResult, BenchmarkResult
from src.domain.interfaces.graph_adapter import GraphAdapter
from src.utils.logger import step_logger

class RetrievalService:
    """
    High-level service for orchestrating retrieval strategies.
    
    Provides:
    - Strategy selection and execution
    - Context windowing
    - Result filtering and ranking
    - Multi-strategy search and comparison
    - Benchmarking capabilities
    """
    
    def __init__(self, adapter: GraphAdapter, strategies: Dict[str, RetrievalStrategy]):
        """
        Args:
            adapter: Graph adapter for additional queries (implements GraphAdapter)
            strategies: Dict mapping strategy names to strategy instances
        """
        self.adapter = adapter
        self.strategies = strategies
        
        step_logger.info(f"[RetrievalService] Initialized with {len(strategies)} strategies: "
                        f"{list(strategies.keys())}")
    
    def search(self, query: str, strategy: str = "hybrid", top_k: int = 10, 
              **kwargs) -> List[SearchResult]:
        """
        Perform a search using the specified strategy.
        
        Args:
            query: Search query
            strategy: Name of strategy to use ("vector", "keyword", "hybrid", "graph", "llm")
            top_k: Number of results to return
            **kwargs: Strategy-specific parameters
            
        Returns:
            List of SearchResult objects
        """
        if strategy not in self.strategies:
            step_logger.error(f"[RetrievalService] Unknown strategy: {strategy}")
            available = list(self.strategies.keys())
            raise ValueError(f"Unknown strategy '{strategy}'. Available: {available}")
        
        step_logger.info(f"[RetrievalService] Executing '{strategy}' search for: '{query}'")
        
        strategy_instance = self.strategies[strategy]
        results = strategy_instance.search(query, top_k=top_k, **kwargs)
        
        step_logger.info(f"[RetrievalService] Found {len(results)} results")
        
        return results
    
    def search_with_context(self, query: str, strategy: str = "hybrid", 
                           top_k: int = 10, context_window: int = 2,
                           **kwargs) -> List[SearchResult]:
        """
        Perform search and enrich results with surrounding articles.
        
        Args:
            query: Search query
            strategy: Name of strategy to use
            top_k: Number of results to return
            context_window: Number of surrounding articles to fetch
            **kwargs: Strategy-specific parameters
            
        Returns:
            List of SearchResult objects with context included in metadata
        """
        step_logger.info(f"[RetrievalService] Search with context (window={context_window})")
        
        # Perform base search
        results = self.search(query, strategy=strategy, top_k=top_k, **kwargs)
        
        # Enrich with context
        enriched_results = []
        for result in results:
            context_data = self.adapter.get_article_with_context(
                article_id=result.article_id,
                context_window=context_window
            )
            
            if context_data:
                result.metadata["surrounding_articles"] = context_data.get("surrounding_articles", [])
                result.metadata["context_window"] = context_window
            
            enriched_results.append(result)
        
        step_logger.info(f"[RetrievalService] Enriched {len(enriched_results)} results with context")
        
        return enriched_results
    
    def multi_strategy_search(self, query: str, strategies: Optional[List[str]] = None,
                             top_k: int = 10, **kwargs) -> Dict[str, List[SearchResult]]:
        """
        Run the same query across multiple strategies for comparison.
        
        Args:
            query: Search query
            strategies: List of strategy names (None = use all available)
            top_k: Number of results per strategy
            **kwargs: Strategy-specific parameters
            
        Returns:
            Dict mapping strategy names to their results
        """
        if strategies is None:
            strategies = list(self.strategies.keys())
        
        step_logger.info(f"[RetrievalService] Multi-strategy search across: {strategies}")
        
        results_by_strategy = {}
        
        for strategy_name in strategies:
            if strategy_name in self.strategies:
                try:
                    results = self.search(query, strategy=strategy_name, top_k=top_k, **kwargs)
                    results_by_strategy[strategy_name] = results
                except Exception as e:
                    step_logger.error(f"[RetrievalService] Error in {strategy_name}: {e}")
                    results_by_strategy[strategy_name] = []
        
        return results_by_strategy
    
    def benchmark_strategies(self, queries: List[str], 
                           strategies: Optional[List[str]] = None,
                           top_k: int = 10, **kwargs) -> List[BenchmarkResult]:
        """
        Benchmark multiple strategies across multiple queries.
        
        Args:
            queries: List of test queries
            strategies: List of strategy names to benchmark (None = all)
            top_k: Number of results per query
            **kwargs: Strategy-specific parameters
            
        Returns:
            List of BenchmarkResult objects
        """
        if strategies is None:
            strategies = list(self.strategies.keys())
        
        step_logger.info(f"[RetrievalService] Benchmarking {len(strategies)} strategies "
                        f"on {len(queries)} queries")
        
        benchmark_results = []
        
        for strategy_name in strategies:
            if strategy_name not in self.strategies:
                continue
                
            strategy_instance = self.strategies[strategy_name]
            
            for query in queries:
                # Time the search
                start_time = time.time()
                
                try:
                    results = strategy_instance.search(query, top_k=top_k, **kwargs)
                    execution_time_ms = (time.time() - start_time) * 1000
                    
                    benchmark = BenchmarkResult(
                        strategy_name=strategy_name,
                        query=query,
                        num_results=len(results),
                        execution_time_ms=execution_time_ms,
                        results=results,
                        metadata={
                            "top_k": top_k,
                            "avg_score": sum(r.score for r in results) / len(results) if results else 0.0
                        }
                    )
                    benchmark_results.append(benchmark)
                    
                except Exception as e:
                    step_logger.error(f"[RetrievalService] Benchmark error ({strategy_name}, '{query}'): {e}")
                    benchmark = BenchmarkResult(
                        strategy_name=strategy_name,
                        query=query,
                        num_results=0,
                        execution_time_ms=0,
                        results=[],
                        metadata={"error": str(e)}
                    )
                    benchmark_results.append(benchmark)
        
        step_logger.info(f"[RetrievalService] Benchmark complete: {len(benchmark_results)} results")
        
        return benchmark_results
    
    def filter_results(self, results: List[SearchResult], 
                      min_score: Optional[float] = None,
                      valid_only: bool = False,
                      normativa_ids: Optional[List[str]] = None) -> List[SearchResult]:
        """
        Filter search results based on criteria.
        
        Args:
            results: List of SearchResult objects to filter
            min_score: Minimum score threshold
            valid_only: Only include currently valid articles
            normativa_ids: Filter by specific normativa IDs
            
        Returns:
            Filtered list of SearchResult objects
        """
        filtered = results
        
        if min_score is not None:
            filtered = [r for r in filtered if r.score >= min_score]
            step_logger.info(f"[RetrievalService] Filtered by min_score={min_score}: "
                           f"{len(results)} -> {len(filtered)}")
        
        if normativa_ids:
            filtered = [r for r in filtered if r.normativa_id in normativa_ids]
            step_logger.info(f"[RetrievalService] Filtered by normativa_ids: "
                           f"{len(results)} -> {len(filtered)}")
        
        # TODO: Implement valid_only filter (requires date comparison)
        
        return filtered
    
    def get_available_strategies(self) -> List[str]:
        """Get list of available strategy names."""
        return list(self.strategies.keys())
