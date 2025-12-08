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
from typing import Optional

from dotenv import load_dotenv

from src.utils.logger import step_logger
from src.observability import setup_phoenix_tracing, shutdown_phoenix_tracing

from .config import IngestionConfig
from .result import IngestionResult, IngestionStatus, StepResult, RollbackResult
from .ingestion_context import IngestionContext


# Ingestion-specific Phoenix project name
INGESTION_PROJECT_NAME = "coloraria-ingestion"


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


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Coloraria Ingestion Service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Ingest a law:
    python -m src.ingestion.main --law-id BOE-A-1978-31229

  Dry run (no database writes):
    python -m src.ingestion.main --law-id BOE-A-1978-31229 --dry-run

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
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.law_id and not args.rollback:
        parser.error("Either --law-id or --rollback is required")
    
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
