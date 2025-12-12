"""
Pipeline Data Transfer Objects.

Shared models used across the ingestion pipeline stages.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from src.domain.models.normativa import NormativaCons


@dataclass
class DocumentResult:
    """Result of processing a single document."""
    law_id: str
    success: bool
    nodes_created: int = 0
    relationships_created: int = 0
    articles_count: int = 0
    parse_duration: float = 0.0
    embed_duration: float = 0.0
    save_duration: float = 0.0
    duration_seconds: float = 0.0
    error_message: Optional[str] = None


@dataclass 
class BatchIngestionResult:
    """Result of the entire batch ingestion."""
    total_documents: int = 0
    successful: int = 0
    failed: int = 0
    total_nodes: int = 0
    total_relationships: int = 0
    total_reference_links: int = 0
    duration_seconds: float = 0.0
    # Stage timing aggregates (sum of per-doc times)
    total_parse_duration: float = 0.0
    total_embed_duration: float = 0.0
    total_save_duration: float = 0.0
    link_duration: float = 0.0
    # Wall-clock phase durations (first push to poison pill)
    phase_parse_duration: float = 0.0
    phase_embed_duration: float = 0.0
    phase_save_duration: float = 0.0
    document_results: List[DocumentResult] = field(default_factory=list)
    dictionary_stats: Dict[str, int] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_documents": self.total_documents,
            "successful": self.successful,
            "failed": self.failed,
            "total_nodes": self.total_nodes,
            "total_relationships": self.total_relationships,
            "total_reference_links": self.total_reference_links,
            "duration_seconds": self.duration_seconds,
            "stage_timings": {
                "parse": self.total_parse_duration,
                "embed": self.total_embed_duration,
                "save": self.total_save_duration,
                "link": self.link_duration,
            },
            "dictionary_stats": self.dictionary_stats,
            "document_results": [
                {
                    "law_id": r.law_id,
                    "success": r.success,
                    "nodes_created": r.nodes_created,
                    "parse": r.parse_duration,
                    "embed": r.embed_duration,
                    "save": r.save_duration,
                    "error_message": r.error_message
                }
                for r in self.document_results
            ]
        }


@dataclass
class ParsedDocument:
    """Document after CPU parsing phase."""
    law_id: str
    normativa: NormativaCons
    change_events: List[Any]
    parse_duration: float


@dataclass
class EmbeddedDocument:
    """Document after embedding phase (or skipped)."""
    law_id: str
    normativa: NormativaCons
    change_events: List[Any]
    parse_duration: float
    embed_duration: float
