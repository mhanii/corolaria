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
    
    # Default to env var if not provided, else generic default
    if not model_name:
        model_name = os.getenv("LLM_MODEL", "gemini-2.5-flash")
        
    return LLMFactory.create(
        provider=os.getenv("LLM_PROVIDER", "gemini"),
        model=model_name,
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.3")),
        # IMPORTANT: Gemini 2.5 Flash has a "thinking budget" that consumes output tokens
        # before generating the actual response. We need a large buffer to prevent
        # MAX_TOKENS errors with empty content.
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", "8192"))
    )


def create_embedding_provider():
    """Create the embedding provider using the factory pattern."""
    from src.ai.embeddings.factory import EmbeddingFactory
    
    return EmbeddingFactory.create(
        provider="gemini",
        model="models/gemini-embedding-001",
        dimensions=768,
        task_type="RETRIEVAL_QUERY"  # Query type for benchmarks
    )


def create_chat_service(llm_provider, top_k: int = 5, use_exam_prompt: bool = True):
    """
    Create the full RAG chat service following codebase patterns.
    
    Args:
        llm_provider: The LLM provider to use.
        top_k: Number of chunks to retrieve.
        use_exam_prompt: If True, uses an exam-specific prompt (no citations).
    """
    from src.infrastructure.graphdb.connection import Neo4jConnection
    from src.infrastructure.graphdb.adapter import Neo4jAdapter
    from src.domain.services.conversation_service import ConversationService
    from src.domain.services.langgraph_chat_service import LangGraphChatService
    from src.ai.citations.citation_engine import CitationEngine
    from src.benchmarks.services.exam_prompt_builder import ExamPromptBuilder
    from src.ai.prompts.prompt_builder import PromptBuilder
    
    # Create Neo4j connection
    connection = Neo4jConnection(
        uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        user=os.getenv("NEO4J_USER", "neo4j"),
        password=os.getenv("NEO4J_PASSWORD", "password")
    )
    neo4j_adapter = Neo4jAdapter(connection)
    
    # Create embedding provider
    embedding_provider = create_embedding_provider()
    
    # Create conversation service
    conversation_service = ConversationService(
        max_history_messages=int(os.getenv("MAX_HISTORY_MESSAGES", "10")),
        conversation_ttl_hours=int(os.getenv("CONVERSATION_TTL_HOURS", "24"))
    )
    
    # Use exam-specific prompt builder if requested
    prompt_builder = ExamPromptBuilder() if use_exam_prompt else PromptBuilder()
    
    return LangGraphChatService(
        llm_provider=llm_provider,
        neo4j_adapter=neo4j_adapter,
        embedding_provider=embedding_provider,
        conversation_service=conversation_service,
        citation_engine=CitationEngine(),
        prompt_builder=prompt_builder,
        retrieval_top_k=top_k,
        index_name=os.getenv("RETRIEVAL_INDEX_NAME", "article_embeddings")
    )


def run_single_benchmark(
    exam: Exam, 
    model_name: str, 
    top_k: int, 
    use_rag: bool = True,
    llm_provider: Optional[LLMProvider] = None
) -> BenchmarkResult:
    """Run a single benchmark configuration."""
    step_logger.info(f"--- Running Benchmark: Model={model_name}, RAG={use_rag}, TopK={top_k} ---")
    
    # Create the LLM provider if not provided
    if not llm_provider:
        step_logger.info(f"Creating new LLM Provider for {model_name}")
        llm_provider = create_llm_provider(model_name)
    else:
        # Check if we need to check consistency? Assuming caller knows what they are doing.
        pass
    
    # Create chat service if RAG is enabled
    chat_service = None
    if use_rag:
        # Note: We create a fresh service each time to ensure clean state and correct config
        # even if we reuse the LLM provider.
        chat_service = create_chat_service(llm_provider, top_k=top_k, use_exam_prompt=True)
    
    # Create the runner
    runner = BenchmarkRunner(
        llm_provider=llm_provider,
        chat_service=chat_service,
        use_rag=use_rag,
    )
    
    # Run the benchmark
    result = runner.run_exam(
        exam=exam,
        model_name=model_name,
        parameters={"top_k": top_k},
    )
    
    return result


def safe_run_benchmark(exam, model_name, top_k, use_rag, llm_provider=None) -> Optional[Dict]:
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
            llm_provider=llm_provider
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
    
    args = parser.parse_args()
    
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
        model_name = os.getenv("LLM_MODEL", "gemini-2.5-flash")
        res = run_single_benchmark(exam, model_name=model_name, top_k=args.top_k, use_rag=not args.no_rag)
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


if __name__ == "__main__":
    main()
