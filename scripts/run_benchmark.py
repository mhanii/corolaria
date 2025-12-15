#!/usr/bin/env python3
"""
Benchmark Runner CLI.
Runs exams through the RAG pipeline or directly to an LLM and outputs results.

Usage:
    python scripts/run_benchmark.py --exam exam.pdf [--no-rag] [--output results.json]
    
    # Matrix mode:
    python scripts/run_benchmark.py --exam exam.pdf --matrix [--output results.json]
    
Supports both PDF and TXT input files. PDFs are automatically converted to text.
"""
import argparse
import json
import os
import sys
import time
import concurrent.futures
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add project root to path for imports
project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv()

from src.benchmarks.services.parser import ExamParserService
from src.benchmarks.services.runner import BenchmarkRunner
from src.utils.logger import step_logger
from src.benchmarks.domain.schemas import Exam, BenchmarkResult
# Import LLMProvider type for type hinting
from src.domain.interfaces.llm_provider import LLMProvider
# Phoenix tracing for observability
from src.observability import setup_phoenix_tracing, shutdown_phoenix_tracing


def convert_pdf_if_needed(file_path: str, output_dir: str = None) -> str:
    """
    Convert PDF to text if needed. Returns path to text file.
    
    Args:
        file_path: Path to input file (PDF or TXT).
        output_dir: Optional output directory for converted text.
        
    Returns:
        Path to the text file (original if TXT, converted if PDF).
    """
    path = Path(file_path)
    
    if path.suffix.lower() == ".txt":
        return file_path
    
    if path.suffix.lower() == ".pdf":
        try:
            from src.benchmarks.services.pdf_converter import PDFConverterService
        except ImportError as e:
            step_logger.error(f"PDF conversion requires PyMuPDF: pip install pymupdf")
            raise
        
        converter = PDFConverterService()
        
        if output_dir:
            out_path = Path(output_dir) / f"{path.stem}.txt"
        else:
            out_path = path.with_suffix(".txt")
        
        step_logger.info(f"Converting PDF to text: {file_path} -> {out_path}")
        converter.convert_pdf(file_path, str(out_path))
        return str(out_path)
    
    # Assume it's a text file
    return file_path


def create_llm_provider(model_name: str = None):
    """Create the LLM provider using the factory pattern."""
    from src.ai.llm.factory import LLMFactory
    from src.config import get_llm_config, get_benchmark_config
    
    llm_config = get_llm_config()
    bench_config = get_benchmark_config()
    
    # Default selection priority:
    # 1. explicit model_name arg
    # 2. benchmark.model from config
    # 3. llm.model from config
    # 4. hardcoded fallback
    
    if not model_name:
        model_name = bench_config.get("model") or llm_config.get("model", "gemini-2.5-flash")
        
    return LLMFactory.create(
        provider=llm_config.get("provider", "gemini"), # Use main provider config
        model=model_name,
        temperature=float(bench_config.get("temperature") or llm_config.get("temperature", 0.3)),
        # IMPORTANT: Gemini 2.5 Flash has a "thinking budget" that consumes output tokens
        # before generating the actual response. We need a large buffer to prevent
        # MAX_TOKENS errors with empty content.
        max_tokens=int(llm_config.get("max_tokens", 8192))
    )

def create_embedding_provider(cache_path: str = None):
    """Create the embedding provider using the factory pattern."""
    from src.ai.embeddings.factory import EmbeddingFactory
    from src.ai.embeddings.sqlite_cache import SQLiteEmbeddingCache
    
    # Create cache if path provided
    cache = None
    if cache_path:
        cache = SQLiteEmbeddingCache(cache_path)
    
    return EmbeddingFactory.create(
        provider="gemini",
        model="models/gemini-embedding-001",
        dimensions=768,
        task_type="RETRIEVAL_QUERY",  # Query type for benchmarks
        cache=cache
    )


def create_context_collector(cache_path: str = None):
    """
    Create the RAG context collector for benchmarks.
    
    Uses RAGCollector directly to retrieve relevant legal articles
    based on the question text embedding.
    """
    from src.infrastructure.graphdb.connection import Neo4jConnection
    from src.infrastructure.graphdb.adapter import Neo4jAdapter
    from src.ai.context_collectors import RAGCollector
    
    # Create Neo4j connection
    connection = Neo4jConnection(
        uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        user=os.getenv("NEO4J_USER", "neo4j"),
        password=os.getenv("NEO4J_PASSWORD", "password")
    )
    neo4j_adapter = Neo4jAdapter(connection)
    
    # Create embedding provider with cache
    embedding_provider = create_embedding_provider(cache_path)
    
    return RAGCollector(
        neo4j_adapter=neo4j_adapter,
        embedding_provider=embedding_provider,
        index_name=os.getenv("RETRIEVAL_INDEX_NAME", "article_embeddings"),
        enrich=False
    )


def run_single_benchmark(
    exam: Exam, 
    model_name: str, 
    top_k: int, 
    use_rag: bool = True,
    llm_provider: Optional[LLMProvider] = None,
    embed_options: bool = False,
    multi_query: bool = False,
    cache_path: str = None
) -> BenchmarkResult:
    """Run a single benchmark configuration."""
    step_logger.info(f"--- Running Benchmark: Model={model_name}, RAG={use_rag}, TopK={top_k}, EmbedOptions={embed_options}, MultiQuery={multi_query} ---")
    
    # Create the LLM provider if not provided
    if not llm_provider:
        step_logger.info(f"Creating new LLM Provider for {model_name}")
        llm_provider = create_llm_provider(model_name)
    
    # Create context collector if RAG is enabled
    context_collector = None
    if use_rag:
        context_collector = create_context_collector(cache_path)
    
    # Create the runner
    runner = BenchmarkRunner(
        llm_provider=llm_provider,
        context_collector=context_collector,
        use_rag=use_rag,
        embed_options=embed_options,
        multi_query=multi_query,
    )
    
    # Run the benchmark
    result = runner.run_exam(
        exam=exam,
        model_name=model_name,
        parameters={"top_k": top_k},
    )
    
    return result


def safe_run_benchmark(exam, model_name, top_k, use_rag, llm_provider=None, embed_options=False, multi_query=False, cache_path=None) -> Optional[Dict]:
    """Wrapper to run benchmark safely in a thread."""
    try:
        # We need to act carefully with global resources in threads if any,
        # but here most things are instantiated per run.
        # Random sleep to jitter start times and avoid immediate thundering herd on API
        time.sleep(0.5) 
        res = run_single_benchmark(
            exam, 
            model_name=model_name, 
            top_k=top_k, 
            use_rag=use_rag,
            llm_provider=llm_provider,
            embed_options=embed_options,
            multi_query=multi_query,
            cache_path=cache_path
        )
        return res.to_dict()
    except Exception as e:
        step_logger.error(f"Failed run for {model_name} @ top_k={top_k}, RAG={use_rag}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Run LLM benchmarks on exam files (PDF or TXT).")
    parser.add_argument(
        "--exam",
        required=True,
        help="Path to the exam file (PDF or TXT)",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Name for the exam (defaults to file name)",
    )
    parser.add_argument(
        "--no-rag",
        action="store_true",
        help="Run without RAG context (direct LLM)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON file for results",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of RAG chunks to retrieve (default: 5) - ignored in matrix mode",
    )
    parser.add_argument(
        "--text-output-dir",
        default=None,
        help="Directory to save converted text files (for PDFs)",
    )
    parser.add_argument(
        "-q", "--questions",
        type=int,
        default=None,
        help="Limit the number of questions to run (e.g., -q 25 for first 25 questions)",
    )
    parser.add_argument(
        "--matrix",
        action="store_true",
        help="Run matrix benchmark (multiple models x multiple top_k)",
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Enable Phoenix tracing for observability (benchmark tags)",
    )
    parser.add_argument(
        "--embed-options",
        action="store_true",
        help="Include answer options in embedding query (default: question text only)",
    )
    parser.add_argument(
        "--multi-query",
        action="store_true",
        help="Embed question + each option separately, retrieve chunks for each, deduplicate results",
    )
    parser.add_argument(
        "--cache-path",
        default="data/exam_embedding_cache.db",
        help="Path to embedding cache database (default: data/exam_embedding_cache.db)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable embedding cache",
    )
    
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Run in batch mode (async) using Gemini Batch API",
    )
    
    args = parser.parse_args()
    
    # Setup Phoenix tracing if requested
    tracing_enabled = False
    if args.trace:
        tracing_enabled = setup_phoenix_tracing(
            project_name="coloraria-benchmark",
            check_connection=True
        )
        if tracing_enabled:
            step_logger.info("[Benchmark] Phoenix tracing enabled - traces will be tagged with 'benchmark'")
        else:
            step_logger.warning("[Benchmark] Phoenix server not available - continuing without tracing")
    
    # Convert PDF to text if needed
    text_file = convert_pdf_if_needed(args.exam, args.text_output_dir)
    
    # Parse the exam
    step_logger.info(f"Parsing exam: {text_file}")
    exam_parser = ExamParserService()
    exam = exam_parser.parse_file(text_file, exam_name=args.name)
    
    # Limit questions if requested
    if args.questions and args.questions < len(exam.questions):
        step_logger.info(f"Limiting to first {args.questions} questions")
        exam.questions = exam.questions[:args.questions]
    step_logger.info(f"Parsed {len(exam.questions)} questions")
    
    # Show answer key stats
    answered = sum(1 for q in exam.questions if q.correct_answer)
    step_logger.info(f"Answer keys found: {answered}/{len(exam.questions)}")
    
    results_collection = []
    
    # BATCH MODE EXECUTION
    if args.batch:
        from src.benchmarks.services.batch_runner import BatchBenchmarkRunner
        
        step_logger.info("Running in BATCH mode.")
        
        # Create dependencies
        # TODO: Allow model selection for batch
        from src.config import get_llm_config, get_benchmark_config
        model_name = get_benchmark_config().get("model") or get_llm_config().get("model", "gemini-2.5-flash")
        
        llm_provider = create_llm_provider(model_name)
        
        context_collector = None
        if not args.no_rag:
             context_collector = create_context_collector(None if args.no_cache else args.cache_path)
             
        runner = BatchBenchmarkRunner(llm_provider, context_collector)
        
        # Prepare file
        jsonl_path = f"{Path(text_file).stem}_batch_input.jsonl"
        runner.prepare_batch_file(exam, jsonl_path, use_rag=not args.no_rag, top_k=args.top_k)
        
        # Submit
        step_logger.info(f"Submitting batch job for {model_name}...")
        job = runner.submit_batch(jsonl_path, display_name=f"bench-{exam.name}-{int(time.time())}")
        
        print("\n" + "=" * 80)
        print(f"BATCH JOB SUBMITTED: {job.name}")
        print("=" * 80)
        print(f"Exam: {exam.name}")
        print(f"Model: {model_name}")
        print("-" * 80)
        print("Waiting for completion (this may take a while)...")
        
        # Polling loop
        while True:
            job_status = llm_provider.get_batch_job(job.name)
            state = getattr(job_status, 'state', 'UNKNOWN')
            step_logger.info(f"Job State: {state}")
            
            if str(state) == "JobState.JOB_STATE_SUCCEEDED":
                print("\nJob Succeeded! Retrieving results...")
                try:
                    results = runner.process_results(job.name, exam)
                    
                    # Print Summary Table
                    print("\n" + "=" * 80)
                    print(f"BATCH BENCHMARK RESULTS: {exam.name}")
                    print("=" * 80)
                    score = results.get('score_percent', 0.0)
                    print(f"Score: {score:.1f}%")
                    print(f"Correct: {results.get('correct_count')}/{results.get('total_questions')}")
                    print("=" * 80)
                    
                    # Save results
                    if args.output:
                        with open(args.output, "w", encoding="utf-8") as f:
                            json.dump([results], f, ensure_ascii=False, indent=2)
                        step_logger.info(f"Results saved to {args.output}")
                        
                except Exception as e:
                    step_logger.error(f"Failed to process results: {e}")
                    import traceback
                    traceback.print_exc()
                break
                
            elif str(state) in ["JobState.JOB_STATE_FAILED", "JobState.JOB_STATE_CANCELLED"]:
                print(f"\nJob Failed/Cancelled: {getattr(job_status, 'error', 'Unknown error')}")
                break
                
            time.sleep(30) # Poll every 30 seconds
            
        return

    if args.matrix:
        # Matrix Configuration
        models = [
            "gemini-2.0-flash",
            "gemini-2.5-flash",
            "gemini-3-pro-preview"
        ]
        top_k_values = [5, 10, 15, 20]
        
        step_logger.info(f"Starting MATRIX benchmark: {len(models)} models x {len(top_k_values)} top_k values (Parallel execution)")
        
        # Prepare tasks
        tasks = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            # RAG Tasks
            for model_name in models:
                # OPTIMIZATION: Create one provider per model and reuse it for all top_k variations
                step_logger.info(f"Initializing shared provider for {model_name}...")
                try:
                    shared_provider = create_llm_provider(model_name)
                    
                    for k in top_k_values:
                        tasks.append(
                            executor.submit(
                                safe_run_benchmark, 
                                exam=exam, 
                                model_name=model_name, 
                                top_k=k, 
                                use_rag=True,
                                llm_provider=shared_provider
                            )
                        )
                    
                    # Baseline Task (No RAG) - also use shared provider
                    step_logger.info(f"Scheduling baseline for {model_name}...")
                    tasks.append(
                        executor.submit(
                            safe_run_benchmark, 
                            exam=exam, 
                            model_name=model_name, 
                            top_k=0, 
                            use_rag=False,
                            llm_provider=shared_provider
                        )
                    )
                except Exception as e:
                    step_logger.error(f"Failed to initialize provider for {model_name}: {e}")

            step_logger.info(f"Scheduled {len(tasks)} benchmark tasks total.")
            
            # Wait for completion
            for future in concurrent.futures.as_completed(tasks):
                res = future.result()
                if res:
                    results_collection.append(res)
        
    else:
        # Standard Single Run
        from src.config import get_llm_config, get_benchmark_config
        model_name = get_benchmark_config().get("model") or get_llm_config().get("model", "gemini-2.5-flash")
        cache_path = None if args.no_cache else args.cache_path
        res = run_single_benchmark(
            exam, 
            model_name=model_name, 
            top_k=args.top_k, 
            use_rag=not args.no_rag,
            embed_options=args.embed_options,
            multi_query=args.multi_query,
            cache_path=cache_path
        )
        results_collection.append(res.to_dict())

    # Output Aggregated Results
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results_collection, f, ensure_ascii=False, indent=2)
        step_logger.info(f"All results saved to {args.output}")
    
    # Print Summary Table
    print("\n" + "=" * 80)
    print(f"BENCHMARK SUMMARY: {exam.name}")
    print("=" * 80)
    print(f"{'Model':<30} | {'RAG':<5} | {'TopK':<5} | {'Score':<6} | {'Time(s)':<7}")
    print("-" * 80)
    
    # Sort results for cleaner display
    def sort_key(r):
        run = r["run"]
        rag_val = 1 if run.get("use_rag") else 0
        top_k_val = run.get("parameters", {}).get("top_k", 0)
        return (run.get("model_name", ""), rag_val, top_k_val)
        
    results_collection.sort(key=sort_key)
    
    for r in results_collection:
        run_meta = r["run"]
        model = run_meta.get("model_name", "unknown")
        rag = "YES" if run_meta.get("use_rag") else "NO"
        # Extract top_k from parameters, handle if missing
        params = run_meta.get("parameters", {})
        top_k = params.get("top_k", "-")
        
        # Use score_percent
        score = r.get("score_percent", 0.0)
        time_s = r.get("execution_time_ms", 0) / 1000
        
        print(f"{model:<30} | {rag:<5} | {top_k:<5} | {score:>5.1f}% | {time_s:>7.1f}")
    print("=" * 80)
    
    # Shutdown Phoenix tracing if it was enabled
    if tracing_enabled:
        shutdown_phoenix_tracing()
        step_logger.info("[Benchmark] Phoenix tracing shutdown complete")


if __name__ == "__main__":
    main()
