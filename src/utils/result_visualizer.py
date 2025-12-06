from typing import List, Dict, Optional
from src.domain.value_objects.search_result import SearchResult, BenchmarkResult
import json

class ResultVisualizer:
    """
    Utility for visualizing search results in various formats.
    Supports console output, JSON export, and strategy comparison.
    """
    
    # ANSI color codes for terminal output
    COLORS = {
        "HEADER": "\033[95m",
        "BLUE": "\033[94m",
        "CYAN": "\033[96m",
        "GREEN": "\033[92m",
        "YELLOW": "\033[93m",
        "RED": "\033[91m",
        "ENDC": "\033[0m",
        "BOLD": "\033[1m",
        "UNDERLINE": "\033[4m",
    }
    
    @staticmethod
    def print_results(results: List[SearchResult], 
                     max_preview: int = 200,
                     show_metadata: bool = False,
                     use_color: bool = True):
        """
        Pretty-print search results to console.
        
        Args:
            results: List of SearchResult objects
            max_preview: Maximum characters for article text preview
            show_metadata: Whether to display metadata
            use_color: Whether to use ANSI colors
        """
        if not use_color:
            ResultVisualizer.COLORS = {k: "" for k in ResultVisualizer.COLORS}
        
        c = ResultVisualizer.COLORS
        
        # Header
        print(f"\n{c['BOLD']}{c['CYAN']}{'='*80}{c['ENDC']}")
        print(f"{c['BOLD']}Search Results: {len(results)} found{c['ENDC']}")
        if results:
            print(f"Strategy: {c['GREEN']}{results[0].strategy_used}{c['ENDC']}")
        print(f"{c['CYAN']}{'='*80}{c['ENDC']}\n")
        
        if not results:
            print(f"{c['YELLOW']}No results found.{c['ENDC']}\n")
            return
        
        # Results
        for idx, result in enumerate(results, 1):
            # Result header
            score_color = ResultVisualizer._get_score_color(result.score)
            print(f"{c['BOLD']}[{idx}]"
                  f"| Score: {score_color}{result.score:.4f}{c['ENDC']}")
            
            print(f"{c['BLUE']}Article {result.article_number}{c['ENDC']}") 
            
            # Normativa
            print(f"{c['CYAN']}Normativa:{c['ENDC']} {result.normativa_title}")
            print(f"{c['CYAN']}ID:{c['ENDC']} {result.normativa_id}")
            
            # Context path
            context = result.get_context_path_string()
            print(f"{c['CYAN']}Context:{c['ENDC']} {context}")
            
            # Article preview
            preview = result.get_preview(max_preview)
            print(f"{c['CYAN']}Text:{c['ENDC']}")
            # Indent the preview
            for line in preview.split('\n'):
                print(f"        {line}")
            
            # Metadata (optional)
            if result.metadata:
                print(f"{c['YELLOW']}Metadata:{c['ENDC']} {result.metadata}")
            
            print()  # Blank line between results
        
        print(f"{c['CYAN']}{'='*80}{c['ENDC']}\n")
    
    @staticmethod
    def compare_strategies(multi_results: Dict[str, List[SearchResult]], 
                          top_k: int = 5,
                          use_color: bool = True):
        """
        Compare results from multiple strategies side-by-side.
        
        Args:
            multi_results: Dict mapping strategy names to results
            top_k: Number of top results to compare
            use_color: Whether to use ANSI colors
        """
        if not use_color:
            ResultVisualizer.COLORS = {k: "" for k in ResultVisualizer.COLORS}
        
        c = ResultVisualizer.COLORS
        
        print(f"\n{c['BOLD']}{c['HEADER']}{'='*80}{c['ENDC']}")
        print(f"{c['BOLD']}Strategy Comparison (Top {top_k}){c['ENDC']}")
        print(f"{c['HEADER']}{'='*80}{c['ENDC']}\n")
        
        # Summary stats
        for strategy_name, results in multi_results.items():
            avg_score = sum(r.score for r in results) / len(results) if results else 0
            print(f"{c['BOLD']}{strategy_name}:{c['ENDC']} "
                  f"{len(results)} results, avg score: {avg_score:.4f}")
        
        print()
        
        # Compare top results
        print(f"{c['BOLD']}Top {top_k} Results by Strategy:{c['ENDC']}\n")
        
        for strategy_name, results in multi_results.items():
            print(f"{c['GREEN']}{c['BOLD']}{strategy_name}:{c['ENDC']}")
            
            top_results = results[:top_k]
            for idx, result in enumerate(top_results, 1):
                score_color = ResultVisualizer._get_score_color(result.score)
                print(f"  {idx}. Article {result.article_number} "
                      f"({score_color}{result.score:.4f}{c['ENDC']}) - "
                      f"{result.get_preview(80)}")
            
            if not top_results:
                print(f"  {c['YELLOW']}No results{c['ENDC']}")
            
            print()
        
        # Overlap analysis
        article_ids_by_strategy = {
            name: set(r.article_id for r in results[:top_k])
            for name, results in multi_results.items()
        }
        
        if len(article_ids_by_strategy) >= 2:
            print(f"{c['BOLD']}Result Overlap:{c['ENDC']}")
            strategy_names = list(article_ids_by_strategy.keys())
            
            for i in range(len(strategy_names)):
                for j in range(i + 1, len(strategy_names)):
                    s1 = strategy_names[i]
                    s2 = strategy_names[j]
                    overlap = article_ids_by_strategy[s1] & article_ids_by_strategy[s2]
                    overlap_pct = (len(overlap) / top_k * 100) if top_k > 0 else 0
                    print(f"  {s1} ∩ {s2}: {len(overlap)}/{top_k} ({overlap_pct:.1f}%)")
            print()
        
        print(f"{c['HEADER']}{'='*80}{c['ENDC']}\n")
    
    @staticmethod
    def print_benchmark(benchmark_results: List[BenchmarkResult], use_color: bool = True):
        """
        Display benchmark results with performance metrics.
        
        Args:
            benchmark_results: List of BenchmarkResult objects
            use_color: Whether to use ANSI colors
        """
        if not use_color:
            ResultVisualizer.COLORS = {k: "" for k in ResultVisualizer.COLORS}
        
        c = ResultVisualizer.COLORS
        
        print(f"\n{c['BOLD']}{c['YELLOW']}{'='*80}{c['ENDC']}")
        print(f"{c['BOLD']}Benchmark Results{c['ENDC']}")
        print(f"{c['YELLOW']}{'='*80}{c['ENDC']}\n")
        
        # Group by strategy for summary
        by_strategy: Dict[str, List[BenchmarkResult]] = {}
        for result in benchmark_results:
            if result.strategy_name not in by_strategy:
                by_strategy[result.strategy_name] = []
            by_strategy[result.strategy_name].append(result)
        
        # Summary table
        print(f"{c['BOLD']}Performance Summary:{c['ENDC']}\n")
        print(f"{'Strategy':<25} {'Avg Time (ms)':<15} {'Avg Results':<15} {'Avg Score':<15}")
        print("-" * 70)
        
        for strategy_name, results in by_strategy.items():
            avg_time = sum(r.execution_time_ms for r in results) / len(results)
            avg_results = sum(r.num_results for r in results) / len(results)
            avg_score = sum(r.get_avg_score() for r in results) / len(results)
            
            print(f"{strategy_name:<25} {avg_time:<15.2f} {avg_results:<15.1f} {avg_score:<15.4f}")
        
        print()
        
        # Detailed results by query
        print(f"{c['BOLD']}Detailed Results by Query:{c['ENDC']}\n")
        
        # Group by query
        by_query: Dict[str, List[BenchmarkResult]] = {}
        for result in benchmark_results:
            if result.query not in by_query:
                by_query[result.query] = []
            by_query[result.query].append(result)
        
        for query, results in by_query.items():
            print(f"{c['CYAN']}Query: \"{query}\"{c['ENDC']}")
            
            for result in results:
                time_color = c['GREEN'] if result.execution_time_ms < 500 else c['YELLOW']
                print(f"  {result.strategy_name:<25} "
                      f"Time: {time_color}{result.execution_time_ms:>6.2f}ms{c['ENDC']} | "
                      f"Results: {result.num_results:>3} | "
                      f"Avg Score: {result.get_avg_score():.4f}")
            print()
        
        print(f"{c['YELLOW']}{'='*80}{c['ENDC']}\n")
    
    @staticmethod
    def export_results(results: List[SearchResult], 
                      filepath: str,
                      format: str = "json"):
        """
        Export results to file.
        
        Args:
            results: List of SearchResult objects
            filepath: Output file path
            format: Export format ("json", "txt")
        """
        if format == "json":
            data = [
                {
                    "article_id": r.article_id,
                    "article_number": r.article_number,
                    "article_text": r.article_text,
                    "normativa_title": r.normativa_title,
                    "normativa_id": r.normativa_id,
                    "score": r.score,
                    "strategy": r.strategy_used,
                    "context_path": r.get_context_path_string(),
                    "metadata": r.metadata
                }
                for r in results
            ]
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        
        elif format == "txt":
            with open(filepath, 'w', encoding='utf-8') as f:
                for idx, result in enumerate(results, 1):
                    f.write(f"[{idx}] Article {result.article_number} | Score: {result.score:.4f}\n")
                    f.write(f"Normativa: {result.normativa_title}\n")
                    f.write(f"Context: {result.get_context_path_string()}\n")
                    f.write(f"Text: {result.article_text}\n")
                    f.write("\n" + "="*80 + "\n\n")
        
        print(f"Exported {len(results)} results to {filepath}")
    
    @staticmethod
    def _get_score_color(score: float) -> str:
        """Get color code based on score value."""
        c = ResultVisualizer.COLORS
        if score >= 0.7:
            return c['GREEN']
        elif score >= 0.4:
            return c['YELLOW']
        else:
            return c['RED']
