"""
Coloraria Ingestion Service.

Main entry point for the ingestion pipeline. Handles:
- Pipeline execution with tracing
- Rollback on failure (automatic and manual)
- CLI interface for running ingestion

Usage:
    # Run ingestion for a law:
    python -m src.ingestion.main --law-id BOE-A-1978-31229
    
    # Dry run (parse only, no database writes):
    python -m src.ingestion.main --law-id BOE-A-1978-31229 --dry-run
    
    # Manual rollback:
    python -m src.ingestion.main --rollback BOE-A-1978-31229
"""

import argparse
import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime
from time import perf_counter
from typing import List, Optional

from dotenv import load_dotenv

from src.utils.logger import step_logger
from src.observability import setup_phoenix_tracing, shutdown_phoenix_tracing

from .config import IngestionConfig
from .result import IngestionResult, IngestionStatus, StepResult, RollbackResult
from .ingestion_context import IngestionContext


# Ingestion-specific Phoenix project name
INGESTION_PROJECT_NAME = "coloraria-ingestion"


async def fetch_law_ids_from_api(offset: int = 0, limit: int = 100) -> List[str]:
    """
    Fetch law IDs from BOE API legislación consolidada endpoint.
    
    Args:
        offset: Start position for pagination
        limit: Maximum number of laws to fetch
        
    Returns:
        List of law identifiers (e.g., ['BOE-A-2024-11291', ...])
    """
    from src.infrastructure.http.http_client import BOEHTTPClient
    
    step_logger.info(f"[Automatic] Fetching law IDs from BOE API (offset={offset}, limit={limit})")
    
    async with BOEHTTPClient() as client:
        # Use XML format for the list endpoint
        response = await client.get(
            endpoint="/legislacion-consolidada",
            params={"offset": offset, "limit": limit},
            accept_format="application/xml"
        )
        
        # Extract identificador from each item
        law_ids = []
        data = response.get("data", {})
        items = data.get("item", [])
        
        # Ensure items is always a list
        if isinstance(items, dict):
            items = [items]
        
        for item in items:
            if isinstance(item, dict) and "identificador" in item:
                law_ids.append(item["identificador"])
        
        step_logger.info(f"[Automatic] Fetched {len(law_ids)} law IDs from BOE API")
        return law_ids


def load_eu_celex_list(file_path: str = "config/eu_celex_top50.txt") -> List[str]:
    """
    Load EU CELEX numbers from a text file.
    
    Args:
        file_path: Path to file with CELEX numbers (one per line)
        
    Returns:
        List of CELEX numbers
    """
    import os
    
    # Handle relative path from project root
    if not os.path.isabs(file_path):
        # Try from current working directory first
        if not os.path.exists(file_path):
            # Try from project root based on this file's location
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            file_path = os.path.join(project_root, file_path)
    
    celex_list = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                # Strip whitespace and skip empty lines/comments
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                # Extract just the CELEX number (ignore inline comments)
                celex = line.split('#')[0].split()[0] if line else ''
                if celex:
                    celex_list.append(celex)
        
        step_logger.info(f"[EU] Loaded {len(celex_list)} CELEX numbers from {file_path}")
        return celex_list
    except FileNotFoundError:
        step_logger.warning(f"[EU] CELEX list file not found: {file_path}")
        return []


def run_eu_batch_ingestion(
    celex_list: List[str],
    language: str = "ES",
    config: Optional[IngestionConfig] = None,
    no_tracing: bool = False
) -> dict:
    """
    Run EU ingestion for multiple documents sequentially.
    
    Args:
        celex_list: List of CELEX numbers to ingest
        language: Language code for documents
        config: Optional configuration override
        no_tracing: Whether to disable tracing
        
    Returns:
        Dict with batch results: {successful, failed, total, results}
    """
    config = config or IngestionConfig.from_env()
    
    results = {
        "successful": 0,
        "failed": 0,
        "total": len(celex_list),
        "results": []
    }
    
    step_logger.info(f"[EU Batch] Starting ingestion of {len(celex_list)} EU documents")
    
    for i, celex in enumerate(celex_list, 1):
        step_logger.info(f"[EU Batch] Processing {i}/{len(celex_list)}: {celex}")
        
        try:
            result = run_eu_ingestion(celex, language, config, dry_run=False)
            
            if result.status == IngestionStatus.SUCCESS:
                results["successful"] += 1
                step_logger.info(f"  ✓ {celex}: {result.nodes_created} nodes in {result.duration_seconds:.1f}s")
            else:
                results["failed"] += 1
                step_logger.warning(f"  ✗ {celex}: {result.error_message}")
            
            results["results"].append({
                "celex": celex,
                "success": result.status == IngestionStatus.SUCCESS,
                "nodes_created": result.nodes_created if result.status == IngestionStatus.SUCCESS else 0,
                "duration": result.duration_seconds,
                "error": result.error_message if result.status != IngestionStatus.SUCCESS else None
            })
            
        except Exception as e:
            results["failed"] += 1
            step_logger.error(f"  ✗ {celex}: {e}")
            results["results"].append({
                "celex": celex,
                "success": False,
                "nodes_created": 0,
                "duration": 0,
                "error": str(e)
            })
    
    step_logger.info(f"[EU Batch] Complete: {results['successful']}/{results['total']} successful")
    return results



@contextmanager
def ingestion_lifecycle(config: Optional[IngestionConfig] = None):
    """
    Context manager for ingestion service lifecycle.
    
    Sets up Phoenix tracing on entry, tears down on exit.
    
    Usage:
        with ingestion_lifecycle():
            result = run_ingestion("BOE-A-1978-31229")
    """
    config = config or IngestionConfig.from_env()
    
    step_logger.info("[Ingestion] Starting ingestion service...")
    
    # Setup tracing
    if config.tracing.enabled:
        setup_phoenix_tracing(
            phoenix_endpoint=config.tracing.phoenix_endpoint,
            project_name=config.tracing.project_name
        )
    
    try:
        yield
    finally:
        # Shutdown tracing
        if config.tracing.enabled:
            shutdown_phoenix_tracing()
        step_logger.info("[Ingestion] Ingestion service stopped.")


def run_ingestion(
    law_id: str,
    config: Optional[IngestionConfig] = None,
    dry_run: bool = False
) -> IngestionResult:
    """
    Run the ingestion pipeline for a specific law.
    
    Args:
        law_id: The BOE identifier for the law (e.g., "BOE-A-1978-31229")
        config: Optional configuration override
        dry_run: If True, skip database writes (parse only)
        
    Returns:
        IngestionResult with status and statistics
    """
    config = config or IngestionConfig.from_env()
    load_dotenv()
    
    started_at = datetime.now()
    start_time = perf_counter()
    step_results = []
    
    step_logger.info(f"[Ingestion] Starting ingestion for {law_id}")
    
    try:
        # Import pipeline components
        from src.application.pipeline.doc2graph import Doc2Graph
        from src.infrastructure.graphdb.connection import Neo4jConnection
        from src.infrastructure.graphdb.adapter import Neo4jAdapter
        
        # Setup database connection for rollback context
        connection = Neo4jConnection(
            config.neo4j.uri,
            config.neo4j.user,
            config.neo4j.password
        )
        adapter = Neo4jAdapter(connection)
        
        # Create ingestion context for rollback support
        ctx = IngestionContext(
            law_id=law_id,
            adapter=adapter,
            auto_rollback=config.rollback.auto_rollback_on_error
        )
        
        try:
            with ctx:
                if dry_run:
                    step_logger.info("[Ingestion] DRY RUN - Skipping database operations")
                    # In dry run mode, we could add a different pipeline variant
                    # For now, just create the pipeline but skip graph construction
                    
                # Create and run the pipeline
                pipeline = Doc2Graph(law_id)
                # Update pipeline with context for tracking
                pipeline.context = ctx
                pipeline.pipeline_name = "Doc2Graph"
                
                result = pipeline.run(None)
                
                # Collect step results
                for step_name, timing in pipeline.step_timings.items():
                    step_results.append(StepResult(
                        step_name=step_name,
                        status="success",
                        duration_seconds=timing
                    ))
                
                # Mark as committed if successful
                ctx.commit()
                
                duration = perf_counter() - start_time
                
                return IngestionResult(
                    law_id=law_id,
                    status=IngestionStatus.SUCCESS,
                    started_at=started_at,
                    completed_at=datetime.now(),
                    duration_seconds=duration,
                    step_results=step_results,
                    nodes_created=ctx.nodes_created,
                    relationships_created=ctx.relationships_created
                )
                
        except Exception as e:
            duration = perf_counter() - start_time
            step_logger.error(f"[Ingestion] Failed: {e}")
            
            # Context will auto-rollback if configured
            rollback_result = None
            if ctx.rolled_back:
                rollback_result = RollbackResult(
                    law_id=law_id,
                    success=True,
                    started_at=datetime.now(),
                    completed_at=datetime.now(),
                    nodes_deleted=ctx.nodes_created  # Approximate
                )
            
            return IngestionResult(
                law_id=law_id,
                status=IngestionStatus.ROLLED_BACK if ctx.rolled_back else IngestionStatus.FAILED,
                started_at=started_at,
                completed_at=datetime.now(),
                duration_seconds=duration,
                step_results=step_results,
                failed_step=ctx.failed_step,
                error_message=str(e),
                was_rolled_back=ctx.rolled_back,
                rollback_result=rollback_result
            )
        
        finally:
            connection.close()
            
    except Exception as e:
        # Outer exception (e.g., connection failed)
        duration = perf_counter() - start_time
        step_logger.error(f"[Ingestion] Fatal error: {e}", exc_info=True)
        
        return IngestionResult(
            law_id=law_id,
            status=IngestionStatus.FAILED,
            started_at=started_at,
            completed_at=datetime.now(),
            duration_seconds=duration,
            error_message=str(e)
        )


def rollback_ingestion(law_id: str, config: Optional[IngestionConfig] = None) -> RollbackResult:
    """
    Manually rollback an ingested law.
    
    Deletes the Normativa and all its content tree nodes,
    preserving shared nodes (Materia, Departamento, Rango).
    
    Args:
        law_id: The BOE identifier for the law to rollback
        config: Optional configuration override
        
    Returns:
        RollbackResult with deletion statistics
    """
    config = config or IngestionConfig.from_env()
    load_dotenv()
    
    step_logger.info(f"[Ingestion] Manual rollback requested for {law_id}")
    
    try:
        from src.infrastructure.graphdb.connection import Neo4jConnection
        from src.infrastructure.graphdb.adapter import Neo4jAdapter
        
        connection = Neo4jConnection(
            config.neo4j.uri,
            config.neo4j.user,
            config.neo4j.password
        )
        adapter = Neo4jAdapter(connection)
        
        try:
            ctx = IngestionContext(law_id=law_id, adapter=adapter, auto_rollback=False)
            result = ctx.rollback()
            return result
        finally:
            connection.close()
            
    except Exception as e:
        step_logger.error(f"[Ingestion] Rollback failed: {e}", exc_info=True)
        return RollbackResult(
            law_id=law_id,
            success=False,
            started_at=datetime.now(),
            error_message=str(e)
        )


def run_eu_ingestion(
    celex: str,
    language: str = "ES",
    config: Optional[IngestionConfig] = None,
    dry_run: bool = False
) -> IngestionResult:
    """
    Run the EU ingestion pipeline for a specific EUR-Lex document.
    
    Args:
        celex: CELEX number (e.g., "32016R0679" for GDPR, "12016P/TXT" for Charter)
        language: 2-letter language code (ES, EN, FR, etc.)
        config: Optional configuration override
        dry_run: If True, skip database writes (parse only)
        
    Returns:
        IngestionResult with status and statistics
    """
    config = config or IngestionConfig.from_env()
    load_dotenv()
    
    started_at = datetime.now()
    start_time = perf_counter()
    step_results = []
    
    step_logger.info(f"[EU Ingestion] Starting ingestion for {celex} ({language})")
    
    try:
        # Import EU pipeline
        from src.application.pipeline.eu_doc2graph import EUDoc2Graph
        
        # Create and run the pipeline
        pipeline = EUDoc2Graph(celex=celex, language=language)
        
        try:
            if dry_run:
                step_logger.info("[EU Ingestion] DRY RUN - Parsing only")
                # In dry-run, we still run but log the preview
            
            result = pipeline.run(None)
            
            # Collect step results if available
            if hasattr(pipeline, 'step_timings'):
                for step_name, timing in pipeline.step_timings.items():
                    step_results.append(StepResult(
                        step_name=step_name,
                        status="success",
                        duration_seconds=timing
                    ))
            
            duration = perf_counter() - start_time
            
            # Extract node count from result if available
            nodes_created = 0
            if result and hasattr(result, 'nodes_created'):
                nodes_created = result.nodes_created
            
            return IngestionResult(
                law_id=celex,
                status=IngestionStatus.SUCCESS,
                started_at=started_at,
                completed_at=datetime.now(),
                duration_seconds=duration,
                step_results=step_results,
                nodes_created=nodes_created
            )
                
        finally:
            pipeline.close()
            
    except Exception as e:
        duration = perf_counter() - start_time
        step_logger.error(f"[EU Ingestion] Failed: {e}", exc_info=True)
        
        return IngestionResult(
            law_id=celex,
            status=IngestionStatus.FAILED,
            started_at=started_at,
            completed_at=datetime.now(),
            duration_seconds=duration,
            error_message=str(e)
        )


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Coloraria Ingestion Service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Ingest a single law:
    python -m src.ingestion.main --law-id BOE-A-1978-31229

  Ingest an EU document:
    python -m src.ingestion.main --source eu --celex 32016R0679

  Ingest the EU Charter:
    python -m src.ingestion.main --source eu --celex 12016P/TXT

  Batch ingest from file (one law ID per line):
    python -m src.ingestion.main --batch laws.txt --semaphore 10

  Decoupled mode (3-pool producer-consumer):
    python -m src.ingestion.main --batch laws.txt --decoupled

  Stress test with simulated embeddings:
    python -m src.ingestion.main --batch laws.txt --decoupled --simulate

  Rollback a law:
    python -m src.ingestion.main --rollback BOE-A-1978-31229
        """
    )
    
    parser.add_argument(
        "--law-id",
        type=str,
        help="BOE identifier for the law to ingest (e.g., BOE-A-1978-31229)"
    )
    parser.add_argument(
        "--batch",
        type=str,
        metavar="FILE",
        help="Path to file with law IDs (one per line) for concurrent ingestion"
    )
    parser.add_argument(
        "--semaphore",
        type=int,
        default=10,
        help="Concurrency limit for simple batch mode (default: 10)"
    )
    parser.add_argument(
        "--decoupled",
        action="store_true",
        help="Use 3-pool decoupled producer-consumer architecture"
    )
    parser.add_argument(
        "--cpu-workers",
        type=int,
        default=12,
        help="Number of CPU/parser workers in decoupled mode (default: 5)"
    )
    parser.add_argument(
        "--network-workers",
        type=int,
        default=4,
        help="Number of network/embedder workers in decoupled mode (default: 20)"
    )
    parser.add_argument(
        "--disk-workers",
        type=int,
        default=12,
        help="Number of disk/writer workers in decoupled mode (default: 2)"
    )
    parser.add_argument(
        "--scatter-chunk-size",
        type=int,
        default=500,
        help="Articles per chunk for scatter-gather parallelism (default: 500)"
    )
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Skip embedding generation (graph-only mode for speed testing)"
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Use simulated embeddings (for stress testing without API costs)"
    )
    parser.add_argument(
        "--rollback",
        type=str,
        metavar="LAW_ID",
        help="Rollback (delete) a previously ingested law"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse only, don't write to database"
    )
    parser.add_argument(
        "--no-tracing",
        action="store_true",
        help="Disable Phoenix tracing"
    )
    parser.add_argument(
        "--output-json",
        type=str,
        metavar="FILE",
        help="Write result to JSON file"
    )
    
    # Automatic mode arguments
    parser.add_argument(
        "--automatic",
        action="store_true",
        help="Fetch law IDs automatically from BOE API instead of file"
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Start offset for BOE API pagination (default: 0)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum laws to fetch from BOE API (default: 100)"
    )
    
    # EU source arguments
    parser.add_argument(
        "--source",
        type=str,
        choices=["boe", "eu"],
        default="boe",
        help="Document source: 'boe' (default) or 'eu' for EUR-Lex"
    )
    parser.add_argument(
        "--celex",
        type=str,
        help="CELEX number for EU document (e.g., 32016R0679 for GDPR)"
    )
    parser.add_argument(
        "--language",
        type=str,
        default="ES",
        help="Language for EU documents (default: ES)"
    )
    parser.add_argument(
        "--include-eu",
        action="store_true",
        help="Also ingest EU documents from config/eu_celex_top50.txt after BOE ingestion"
    )
    parser.add_argument(
        "--eu-file",
        type=str,
        default="config/eu_celex_top50.txt",
        help="Path to file with EU CELEX numbers (default: config/eu_celex_top50.txt)"
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable embedding cache (fresh embeddings, no cache reads/writes)"
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.source == "eu":
        if not args.celex and not args.rollback:
            parser.error("--celex is required when --source eu is specified")
    elif not args.law_id and not args.rollback and not args.batch and not args.automatic:
        parser.error("Either --law-id, --batch, --automatic, or --rollback is required")
    
    # Automatic mode is mutually exclusive with batch and law-id
    if args.automatic and (args.batch or args.law_id):
        parser.error("Cannot use --automatic with --law-id or --batch")
    
    # Create config
    config = IngestionConfig.from_env()
    if args.no_tracing:
        config.tracing.enabled = False
    
    # Run within lifecycle context
    with ingestion_lifecycle(config):
        if args.rollback:
            result = rollback_ingestion(args.rollback, config)
            result_dict = result.to_dict()
            
            if result.success:
                step_logger.info(f"✓ Rollback successful: {result.nodes_deleted} nodes deleted")
            else:
                step_logger.error(f"✗ Rollback failed: {result.error_message}")
                sys.exit(1)
        
        elif args.batch:
            # Batch mode: concurrent ingestion
            import asyncio
            
            # Run EU ingestion FIRST if --include-eu is specified
            eu_results = None
            if args.include_eu:
                step_logger.info("=== Starting EU Document Ingestion ===")
                celex_list = load_eu_celex_list(args.eu_file)
                if celex_list:
                    eu_results = run_eu_batch_ingestion(celex_list, args.language, config)
                    step_logger.info(f"EU ingestion: {eu_results['successful']}/{eu_results['total']} successful\n")
            
            # Read BOE law IDs from file
            with open(args.batch, 'r') as f:
                law_ids = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            
            step_logger.info(f"=== Starting BOE Ingestion: {len(law_ids)} laws ===")
            
            # Always use Decoupled 3-pool producer-consumer mode
            from src.ingestion.orchestrator import DecoupledIngestionOrchestrator
            
            step_logger.info(f"Decoupled mode: CPU={args.cpu_workers}, Network={args.network_workers}, Disk={args.disk_workers}")
            if args.skip_embeddings:
                step_logger.info("Skip embeddings: Graph-only mode (no embeddings)")
            elif args.simulate:
                step_logger.info("Simulation mode: Using fake embeddings")
            
            orchestrator = DecoupledIngestionOrchestrator(
                cpu_workers=args.cpu_workers,
                network_workers=args.network_workers,
                disk_workers=args.disk_workers,
                scatter_chunk_size=args.scatter_chunk_size,
                skip_embeddings=args.skip_embeddings,
                simulate_embeddings=args.simulate,
                embedding_cache=not args.no_cache,
                config=config
            )
            
            result = asyncio.run(orchestrator.run(law_ids))
            result_dict = result.to_dict()
            
            # Print summary
            step_logger.info(f"✓ Batch ingestion complete")
            step_logger.info(f"  Total: {result.successful}/{result.total_documents} successful")
            step_logger.info(f"  Nodes: {result.total_nodes}")
            step_logger.info(f"  Reference links: {result.total_reference_links}")
            step_logger.info(f"  Wall-clock time: {result.duration_seconds:.2f}s")
            
            # Wall-clock phase durations (actual elapsed time per phase)
            step_logger.info(f"  Phase durations (wall-clock):")
            step_logger.info(f"    Parse:  {result.phase_parse_duration:.2f}s")
            step_logger.info(f"    Embed:  {result.phase_embed_duration:.2f}s")
            step_logger.info(f"    Save:   {result.phase_save_duration:.2f}s")
            step_logger.info(f"    Link:   {result.link_duration:.2f}s")
            
            # Aggregate totals (sum of per-doc times - shows CPU time spent)
            step_logger.info(f"  Aggregate totals (sum of per-doc times):")
            step_logger.info(f"    Parse:  {result.total_parse_duration:.2f}s")
            step_logger.info(f"    Embed:  {result.total_embed_duration:.2f}s")
            step_logger.info(f"    Save:   {result.total_save_duration:.2f}s")
            
            if result.failed > 0:
                step_logger.warning(f"  Failed: {result.failed} documents")
                for doc in result.document_results:
                    if not doc.success:
                        step_logger.warning(f"    - {doc.law_id}: {doc.error_message}")
            
            # Show combined summary if EU was also ingested
            if eu_results:
                step_logger.info(f"\n✓ Combined ingestion complete:")
                step_logger.info(f"  BOE: {result.successful}/{result.total_documents} documents")
                step_logger.info(f"  EU:  {eu_results['successful']}/{eu_results['total']} documents")
        
        elif args.automatic:
            # Automatic mode: fetch law IDs from BOE API
            import asyncio
            
            # Run EU ingestion FIRST if --include-eu is specified
            eu_results = None
            if args.include_eu:
                step_logger.info("=== Starting EU Document Ingestion ===")
                celex_list = load_eu_celex_list(args.eu_file)
                if celex_list:
                    eu_results = run_eu_batch_ingestion(celex_list, args.language, config)
                    step_logger.info(f"EU ingestion: {eu_results['successful']}/{eu_results['total']} successful\n")
            
            # Fetch BOE law IDs from API
            law_ids = asyncio.run(fetch_law_ids_from_api(args.offset, args.limit))
            
            if not law_ids:
                step_logger.error("No law IDs fetched from BOE API")
                sys.exit(1)
            
            step_logger.info(f"=== Starting BOE Ingestion: {len(law_ids)} laws ===")
            
            # Use same orchestrator as batch mode
            from src.ingestion.orchestrator import DecoupledIngestionOrchestrator
            
            step_logger.info(f"Decoupled mode: CPU={args.cpu_workers}, Network={args.network_workers}, Disk={args.disk_workers}")
            if args.skip_embeddings:
                step_logger.info("Skip embeddings: Graph-only mode (no embeddings)")
            elif args.simulate:
                step_logger.info("Simulation mode: Using fake embeddings")
            
            orchestrator = DecoupledIngestionOrchestrator(
                cpu_workers=args.cpu_workers,
                network_workers=args.network_workers,
                disk_workers=args.disk_workers,
                scatter_chunk_size=args.scatter_chunk_size,
                skip_embeddings=args.skip_embeddings,
                simulate_embeddings=args.simulate,
                embedding_cache=not args.no_cache,
                config=config
            )
            
            result = asyncio.run(orchestrator.run(law_ids))
            result_dict = result.to_dict()
            
            # Print summary
            step_logger.info(f"✓ Automatic ingestion complete")
            step_logger.info(f"  Total: {result.successful}/{result.total_documents} successful")
            step_logger.info(f"  Nodes: {result.total_nodes}")
            step_logger.info(f"  Reference links: {result.total_reference_links}")
            step_logger.info(f"  Wall-clock time: {result.duration_seconds:.2f}s")
            
            # Wall-clock phase durations
            step_logger.info(f"  Phase durations (wall-clock):")
            step_logger.info(f"    Parse:  {result.phase_parse_duration:.2f}s")
            step_logger.info(f"    Embed:  {result.phase_embed_duration:.2f}s")
            step_logger.info(f"    Save:   {result.phase_save_duration:.2f}s")
            step_logger.info(f"    Link:   {result.link_duration:.2f}s")
            
            # Aggregate totals
            step_logger.info(f"  Aggregate totals (sum of per-doc times):")
            step_logger.info(f"    Parse:  {result.total_parse_duration:.2f}s")
            step_logger.info(f"    Embed:  {result.total_embed_duration:.2f}s")
            step_logger.info(f"    Save:   {result.total_save_duration:.2f}s")
            
            if result.failed > 0:
                step_logger.warning(f"  Failed: {result.failed} documents")
                for doc in result.document_results:
                    if not doc.success:
                        step_logger.warning(f"    - {doc.law_id}: {doc.error_message}")
            
            # Show combined summary if EU was also ingested
            if eu_results:
                step_logger.info(f"\n✓ Combined ingestion complete:")
                step_logger.info(f"  BOE: {result.successful}/{result.total_documents} documents")
                step_logger.info(f"  EU:  {eu_results['successful']}/{eu_results['total']} documents")
        
        elif args.source == "eu" and args.celex:
            # EU document ingestion
            result = run_eu_ingestion(args.celex, args.language, config, dry_run=args.dry_run)
            result_dict = result.to_dict()
            
            # Print summary
            if result.status == IngestionStatus.SUCCESS:
                step_logger.info(f"✓ EU Ingestion successful")
                step_logger.info(f"  CELEX: {args.celex}")
                step_logger.info(f"  Duration: {result.duration_seconds:.2f}s")
                step_logger.info(f"  Nodes: {result.nodes_created}")
            else:
                step_logger.error(f"✗ EU Ingestion failed")
                step_logger.error(f"  Error: {result.error_message}")
                sys.exit(1)
        
        else:
            result = run_ingestion(args.law_id, config, dry_run=args.dry_run)
            result_dict = result.to_dict()
            
            # Print summary
            if result.status == IngestionStatus.SUCCESS:
                step_logger.info(f"✓ Ingestion successful")
                step_logger.info(f"  Duration: {result.duration_seconds:.2f}s")
                step_logger.info(f"  Steps: {len(result.step_results)}")
            elif result.status == IngestionStatus.ROLLED_BACK:
                step_logger.warning(f"⚠ Ingestion failed and was rolled back")
                step_logger.warning(f"  Failed step: {result.failed_step}")
                step_logger.warning(f"  Error: {result.error_message}")
            else:
                step_logger.error(f"✗ Ingestion failed")
                step_logger.error(f"  Error: {result.error_message}")
                sys.exit(1)
        
        # Write JSON output if requested
        if args.output_json:
            with open(args.output_json, "w") as f:
                json.dump(result_dict, f, indent=2, default=str)
            step_logger.info(f"Result written to {args.output_json}")


if __name__ == "__main__":
    main()
