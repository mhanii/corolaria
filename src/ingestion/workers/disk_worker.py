"""
Disk Worker - Neo4j Persistence.

Handles the disk-bound saving phase of the ingestion pipeline.
"""
from time import perf_counter
from typing import Dict, Any

from src.ingestion.models import EmbeddedDocument, DocumentResult
from src.utils.logger import step_logger


def save_to_neo4j_sync(
    embedded: EmbeddedDocument,
    adapter
) -> DocumentResult:
    """
    Synchronous Neo4j save (runs in Disk thread pool).
    
    Saves the normativa and change events to Neo4j.
    
    Args:
        embedded: Document with embeddings (or skipped)
        adapter: Neo4j adapter for database operations
        
    Returns:
        DocumentResult with save statistics
    """
    start_time = perf_counter()
    
    from src.domain.repository.normativa_repository import NormativaRepository
    from src.domain.repository.change_repository import ChangeRepository
    
    normativa_repo = NormativaRepository(adapter)
    save_result = normativa_repo.save_normativa(embedded.normativa)
    
    if embedded.change_events:
        change_repo = ChangeRepository(adapter)
        change_repo.save_change_events(embedded.change_events, normativa_id=save_result["doc_id"])
    
    save_duration = perf_counter() - start_time
    total_duration = embedded.parse_duration + embedded.embed_duration + save_duration
    
    return DocumentResult(
        law_id=embedded.law_id,
        success=True,
        nodes_created=save_result["nodes_created"],
        relationships_created=save_result["relationships_created"],
        articles_count=save_result.get("tree_nodes", 0),
        parse_duration=embedded.parse_duration,
        embed_duration=embedded.embed_duration,
        save_duration=save_duration,
        duration_seconds=total_duration
    )
