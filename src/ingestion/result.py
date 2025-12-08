"""
Ingestion Result Types.

Dataclasses for representing the results of ingestion and rollback operations.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class IngestionStatus(Enum):
    """Status of an ingestion operation."""
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    PARTIAL = "partial"  # Some steps succeeded, some failed


@dataclass
class StepResult:
    """Result of a single pipeline step."""
    step_name: str
    status: str  # "success", "failed", "skipped"
    duration_seconds: float
    input_summary: Optional[str] = None
    output_summary: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IngestionResult:
    """
    Result of an ingestion operation.
    
    Contains status, timing, statistics, and step-by-step results.
    """
    law_id: str
    status: IngestionStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    
    # Step results
    step_results: List[StepResult] = field(default_factory=list)
    failed_step: Optional[str] = None
    error_message: Optional[str] = None
    
    # Statistics
    nodes_created: int = 0
    relationships_created: int = 0
    embeddings_generated: int = 0
    embeddings_from_cache: int = 0
    
    # Rollback info
    was_rolled_back: bool = False
    rollback_result: Optional["RollbackResult"] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "law_id": self.law_id,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "step_results": [
                {
                    "step_name": sr.step_name,
                    "status": sr.status,
                    "duration_seconds": sr.duration_seconds,
                    "error_message": sr.error_message,
                }
                for sr in self.step_results
            ],
            "failed_step": self.failed_step,
            "error_message": self.error_message,
            "nodes_created": self.nodes_created,
            "relationships_created": self.relationships_created,
            "embeddings_generated": self.embeddings_generated,
            "embeddings_from_cache": self.embeddings_from_cache,
            "was_rolled_back": self.was_rolled_back,
        }


@dataclass
class RollbackResult:
    """
    Result of a rollback operation.
    
    Contains what was deleted and any errors encountered.
    """
    law_id: str
    success: bool
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    
    # What was deleted
    nodes_deleted: int = 0
    relationships_deleted: int = 0
    
    # Errors
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "law_id": self.law_id,
            "success": self.success,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "nodes_deleted": self.nodes_deleted,
            "relationships_deleted": self.relationships_deleted,
            "error_message": self.error_message,
        }
