"""
CPU Worker - Document Fetching and Parsing.

Handles the CPU-bound parsing phase of the ingestion pipeline.
"""
from time import perf_counter
from typing import Optional

from src.ingestion.models import ParsedDocument
from src.utils.logger import step_logger


def parse_document_sync(law_id: str, enable_table_parsing: bool = False) -> Optional[ParsedDocument]:
    """
    Synchronous document parsing (runs in CPU thread pool).
    
    Fetches raw XML from BOE API and parses to domain model.
    
    Args:
        law_id: BOE document identifier (e.g., "BOE-A-1978-31229")
        enable_table_parsing: Whether to save table content to nodes (default False)
        
    Returns:
        ParsedDocument if successful, None if fetch/parse failed
    """
    start_time = perf_counter()
    
    from src.application.pipeline.data_ingestion import DataRetriever
    from src.application.pipeline.data_processing import DataProcessor
    
    # Fetch from API
    retriever = DataRetriever(name="retriever", search_criteria=law_id)
    raw_data = retriever.process(None)
    
    if not raw_data or not raw_data.get("data"):
        step_logger.warning(f"[CPU] {law_id}: No data from API")
        return None
    
    # Parse to domain model (with table parsing flag)
    processor = DataProcessor(name="processor", enable_table_parsing=enable_table_parsing)
    normativa, change_events = processor.process(raw_data)
    
    if not normativa:
        step_logger.warning(f"[CPU] {law_id}: Failed to parse normativa")
        return None
    
    return ParsedDocument(
        law_id=law_id,
        normativa=normativa,
        change_events=change_events or [],
        parse_duration=perf_counter() - start_time
    )
