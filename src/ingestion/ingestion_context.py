"""
Ingestion Context for Rollback Support.

Provides a context manager that tracks ingestion state and enables
both automatic (on exception) and manual rollback of graph data.
"""

from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime
from time import perf_counter
from typing import Optional, TYPE_CHECKING

from src.utils.logger import step_logger
from .result import RollbackResult

if TYPE_CHECKING:
    from src.infrastructure.graphdb.adapter import Neo4jAdapter


class IngestionContext:
    """
    Tracks ingestion state for rollback support.
    
    This context manager monitors the ingestion process and enables rollback
    of all changes if an error occurs or if manually triggered.
    
    Rollback Strategy:
    - Deletes all nodes connected to the Normativa via PART_OF (content tree)
    - Deletes the Normativa node itself
    - PRESERVES shared nodes (Materia, Departamento, Rango)
    
    Usage:
        adapter = Neo4jAdapter(connection)
        ctx = IngestionContext("BOE-A-1978-31229", adapter)
        
        try:
            with ctx:
                # Run pipeline steps
                ctx.record_step("data_retriever", duration=1.5)
                ctx.record_step("graph_construction", nodes_created=150)
                
                # Mark as committed if all steps succeed
                ctx.commit()
        except Exception:
            # Automatic rollback happens in __exit__
            pass
        
        # Or manual rollback:
        result = ctx.rollback()
    """
    
    def __init__(self, law_id: str, adapter: "Neo4jAdapter", auto_rollback: bool = True):
        """
        Initialize ingestion context.
        
        Args:
            law_id: The normativa ID being ingested (e.g., "BOE-A-1978-31229")
            adapter: Neo4j adapter for database operations
            auto_rollback: If True, automatically rollback on exception
        """
        self.law_id = law_id
        self.adapter = adapter
        self.auto_rollback = auto_rollback
        
        # State tracking
        self.committed = False
        self.rolled_back = False
        self.steps_completed: list[dict] = []
        self.current_step: Optional[str] = None
        self.failed_step: Optional[str] = None
        self.error: Optional[Exception] = None
        
        # Statistics
        self.nodes_created = 0
        self.relationships_created = 0
        
        # Timing
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
    
    def __enter__(self) -> "IngestionContext":
        """Enter the context - start tracking."""
        self.started_at = datetime.now()
        step_logger.info(f"[IngestionContext] Started tracking ingestion for {self.law_id}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """
        Exit the context - handle rollback if needed.
        
        Returns False to propagate exceptions after handling.
        """
        self.completed_at = datetime.now()
        
        if exc_type is not None:
            # An exception occurred
            self.error = exc_val
            step_logger.error(f"[IngestionContext] Ingestion failed: {exc_val}")
            
            if self.auto_rollback and not self.committed and not self.rolled_back:
                step_logger.info(f"[IngestionContext] Auto-rollback triggered for {self.law_id}")
                try:
                    self.rollback()
                except Exception as rollback_error:
                    step_logger.error(f"[IngestionContext] Rollback failed: {rollback_error}")
            
            return False  # Don't suppress the exception
        
        if not self.committed:
            step_logger.warning(f"[IngestionContext] Context exited without commit for {self.law_id}")
        
        return False
    
    def record_step(
        self, 
        step_name: str, 
        duration: float = 0.0,
        nodes_created: int = 0,
        relationships_created: int = 0,
        **metadata
    ) -> None:
        """
        Record completion of a pipeline step.
        
        Args:
            step_name: Name of the completed step
            duration: Time taken in seconds
            nodes_created: Number of nodes created in this step
            relationships_created: Number of relationships created
            **metadata: Additional metadata to record
        """
        self.steps_completed.append({
            "step_name": step_name,
            "duration": duration,
            "nodes_created": nodes_created,
            "relationships_created": relationships_created,
            "completed_at": datetime.now().isoformat(),
            **metadata
        })
        self.nodes_created += nodes_created
        self.relationships_created += relationships_created
        self.current_step = None
        step_logger.debug(f"[IngestionContext] Recorded step: {step_name}")
    
    def mark_step_started(self, step_name: str) -> None:
        """Mark a step as currently running."""
        self.current_step = step_name
    
    def mark_failed(self, step_name: str, error: Exception) -> None:
        """Mark a step as failed."""
        self.failed_step = step_name
        self.error = error
        self.current_step = None
        step_logger.error(f"[IngestionContext] Step '{step_name}' failed: {error}")
    
    def commit(self) -> None:
        """
        Mark the ingestion as successfully committed.
        
        Call this after all pipeline steps complete successfully
        to prevent automatic rollback.
        """
        self.committed = True
        step_logger.info(f"[IngestionContext] Ingestion committed for {self.law_id}")
    
    def rollback(self) -> RollbackResult:
        """
        Delete the normativa and its content tree, preserving shared nodes.
        
        This deletes:
        - All nodes connected to Normativa via PART_OF (content tree)
        - The Normativa node itself
        
        This preserves:
        - Materia, Departamento, Rango nodes (shared between normativas)
        
        Returns:
            RollbackResult with deletion statistics
        """
        if self.rolled_back:
            step_logger.warning(f"[IngestionContext] Already rolled back {self.law_id}")
            return RollbackResult(
                law_id=self.law_id,
                success=True,
                started_at=datetime.now(),
                completed_at=datetime.now(),
                error_message="Already rolled back"
            )
        
        started_at = datetime.now()
        start_time = perf_counter()
        nodes_deleted = 0
        
        step_logger.info(f"[IngestionContext] Rolling back {self.law_id}...")
        
        try:
            # Step 1: Delete content tree (articles, títulos, capítulos, etc.)
            # These are nodes that have PART_OF relationships leading to the Normativa
            delete_tree_query = """
            MATCH (n)-[:PART_OF*]->(normativa:Normativa {id: $law_id})
            WITH n
            DETACH DELETE n
            RETURN count(n) as deleted_count
            """
            
            result = self.adapter.conn.execute_write(
                delete_tree_query, 
                {"law_id": self.law_id}
            )
            tree_deleted = result["deleted_count"] if result else 0
            nodes_deleted += tree_deleted
            step_logger.info(f"[IngestionContext] Deleted {tree_deleted} content tree nodes")
            
            # Step 2: Delete the Normativa node itself
            # DETACH DELETE removes all relationships automatically
            delete_normativa_query = """
            MATCH (normativa:Normativa {id: $law_id})
            DETACH DELETE normativa
            RETURN count(normativa) as deleted_count
            """
            
            result = self.adapter.conn.execute_write(
                delete_normativa_query, 
                {"law_id": self.law_id}
            )
            normativa_deleted = result["deleted_count"] if result else 0
            nodes_deleted += normativa_deleted
            step_logger.info(f"[IngestionContext] Deleted Normativa node")
            
            # Mark as rolled back
            self.rolled_back = True
            
            end_time = perf_counter()
            completed_at = datetime.now()
            
            step_logger.info(
                f"[IngestionContext] Rollback complete: {nodes_deleted} nodes deleted "
                f"in {end_time - start_time:.2f}s"
            )
            
            return RollbackResult(
                law_id=self.law_id,
                success=True,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=end_time - start_time,
                nodes_deleted=nodes_deleted,
            )
            
        except Exception as e:
            end_time = perf_counter()
            step_logger.error(f"[IngestionContext] Rollback failed: {e}")
            
            return RollbackResult(
                law_id=self.law_id,
                success=False,
                started_at=started_at,
                completed_at=datetime.now(),
                duration_seconds=end_time - start_time,
                nodes_deleted=nodes_deleted,
                error_message=str(e)
            )


def create_rollback_context(law_id: str, auto_rollback: bool = True) -> IngestionContext:
    """
    Factory function to create an IngestionContext with a fresh adapter.
    
    Use this when you need a standalone context without an existing adapter.
    
    Args:
        law_id: The normativa ID to track
        auto_rollback: If True, automatically rollback on exception
        
    Returns:
        Configured IngestionContext
    """
    import os
    from dotenv import load_dotenv
    from src.infrastructure.graphdb.connection import Neo4jConnection
    from src.infrastructure.graphdb.adapter import Neo4jAdapter
    
    load_dotenv()
    
    connection = Neo4jConnection(
        os.getenv("NEO4J_URI"),
        os.getenv("NEO4J_USER"),
        os.getenv("NEO4J_PASSWORD")
    )
    adapter = Neo4jAdapter(connection)
    
    return IngestionContext(law_id, adapter, auto_rollback)
