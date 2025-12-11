"""
Concurrent Ingestion Orchestrator.

Coordinates the 3-stage concurrent ingestion pipeline:
1. Pre-load dictionary nodes (Materia, Departamento, Rango)
2. Concurrent document processing with ThreadPoolExecutor
3. Bulk reference linking post-graph-build
4. Vector index rebuild

IMPORTANT: Uses ThreadPoolExecutor because all pipeline operations
(HTTP, SQLite, Neo4j) are blocking I/O. Using async with blocking
calls would block the event loop and run sequentially.

Usage:
    from src.ingestion.concurrent_orchestrator import ConcurrentIngestionOrchestrator
    
    orchestrator = ConcurrentIngestionOrchestrator(semaphore_limit=10)
    await orchestrator.run(["BOE-A-1978-31229", "BOE-A-1889-4763", ...])
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from time import perf_counter
from typing import List, Optional, Dict, Any

from src.infrastructure.graphdb.connection import Neo4jConnection
from src.infrastructure.graphdb.adapter import Neo4jAdapter
from src.ai.embeddings.factory import EmbeddingFactory
from src.ai.embeddings.sqlite_cache import SQLiteEmbeddingCache
from src.ai.indexing.factory import IndexerFactory
from src.domain.value_objects.embedding_config import EmbeddingConfig
from src.utils.logger import step_logger

from .dictionary_preloader import DictionaryPreloader
from .config import IngestionConfig


@dataclass
class DocumentResult:
    """Result of processing a single document."""
    law_id: str
    success: bool
    nodes_created: int = 0
    relationships_created: int = 0
    articles_count: int = 0
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
            "dictionary_stats": self.dictionary_stats,
            "document_results": [
                {
                    "law_id": r.law_id,
                    "success": r.success,
                    "nodes_created": r.nodes_created,
                    "duration_seconds": r.duration_seconds,
                    "error_message": r.error_message
                }
                for r in self.document_results
            ]
        }


class ConcurrentIngestionOrchestrator:
    """
    Orchestrates 3-stage concurrent ingestion:
    
    Stage 0: Pre-load dictionary nodes (prevents deadlocks)
    Stage 1: Concurrent document processing via ThreadPoolExecutor
    Stage 2: Bulk reference linking (after all docs ingested)
    Stage 3: Rebuild vector index (DROP at start, CREATE at end)
    
    Uses ThreadPoolExecutor (not async) because all operations are
    blocking I/O (HTTP, SQLite, Neo4j TCP).
    """
    
    def __init__(
        self,
        semaphore_limit: int = 10,
        batch_size: int = 5000,
        config: Optional[IngestionConfig] = None
    ):
        self.semaphore_limit = semaphore_limit
        self.batch_size = batch_size
        self.config = config or IngestionConfig.from_env()
        
        # Embedding configuration
        self.embedding_config = EmbeddingConfig(
            model_name="models/gemini-embedding-001",
            dimensions=768,
            similarity="cosine",
            task_type="RETRIEVAL_DOCUMENT"
        )
        
        # Will be initialized in run()
        self._connection: Optional[Neo4jConnection] = None
        self._adapter: Optional[Neo4jAdapter] = None
        self._indexer = None
        
        # Shared resources for workers - created once, used by all threads
        self._embedding_cache: Optional[SQLiteEmbeddingCache] = None
        self._embedding_provider = None
        
    async def run(self, law_ids: List[str]) -> BatchIngestionResult:
        """
        Execute the full 3-stage ingestion pipeline.
        
        Args:
            law_ids: List of BOE law identifiers to ingest
            
        Returns:
            BatchIngestionResult with statistics
        """
        start_time = perf_counter()
        result = BatchIngestionResult(total_documents=len(law_ids))
        
        step_logger.info(f"[Orchestrator] Starting batch ingestion of {len(law_ids)} documents")
        step_logger.info(f"[Orchestrator] Concurrency limit: {self.semaphore_limit} threads")
        
        try:
            # Initialize shared Neo4j connection
            self._connection = Neo4jConnection(
                self.config.neo4j.uri,
                self.config.neo4j.user,
                self.config.neo4j.password
            )
            self._adapter = Neo4jAdapter(self._connection)
            
            # Initialize shared embedding resources ONCE (thread-safe)
            self._embedding_cache = SQLiteEmbeddingCache("data/embeddings_cache.db")
            self._embedding_provider = EmbeddingFactory.create(
                provider="gemini",
                model=self.embedding_config.model_name,
                dimensions=self.embedding_config.dimensions,
                task_type=self.embedding_config.task_type
            )
            
            # Ensure constraints exist
            self._adapter.ensure_constraints()
            
            # Initialize indexer
            self._indexer = IndexerFactory.create(
                "neo4j", 
                self.embedding_config, 
                adapter=self._adapter
            )
            
            # Stage 0: Drop vector index for faster writes
            step_logger.info("[Orchestrator] Stage 0: Dropping vector index...")
            self._indexer.drop_index()
            
            # Stage 0: Pre-load dictionary nodes
            step_logger.info("[Orchestrator] Stage 0: Pre-loading dictionary nodes...")
            preloader = DictionaryPreloader(self._adapter)
            result.dictionary_stats = preloader.preload_all()
            
            # Stage 1: Concurrent document processing with ThreadPoolExecutor
            step_logger.info("[Orchestrator] Stage 1: Concurrent document processing...")
            doc_results = await self._process_documents_concurrently(law_ids)
            result.document_results = doc_results
            
            # Calculate stats
            for doc_result in doc_results:
                if doc_result.success:
                    result.successful += 1
                    result.total_nodes += doc_result.nodes_created
                    result.total_relationships += doc_result.relationships_created
                else:
                    result.failed += 1
            
            # Stage 2: Bulk reference linking
            step_logger.info("[Orchestrator] Stage 2: Bulk reference linking...")
            result.total_reference_links = self._bulk_link_references()
            
            # Stage 3: Rebuild vector index
            step_logger.info("[Orchestrator] Stage 3: Creating vector index...")
            self._indexer.create_index()
            
            result.duration_seconds = perf_counter() - start_time
            step_logger.info(
                f"[Orchestrator] Complete. "
                f"{result.successful}/{result.total_documents} successful, "
                f"{result.total_nodes} nodes, "
                f"{result.total_reference_links} reference links, "
                f"{result.duration_seconds:.2f}s"
            )
            
        finally:
            if self._connection:
                self._connection.close()
                
        return result
    
    async def _process_documents_concurrently(
        self, 
        law_ids: List[str]
    ) -> List[DocumentResult]:
        """
        Process documents concurrently using ThreadPoolExecutor.
        
        Uses threads (not async) because all pipeline operations are
        blocking I/O (HTTP requests, SQLite, Neo4j TCP calls).
        """
        loop = asyncio.get_running_loop()
        
        # Create executor with semaphore_limit workers
        with ThreadPoolExecutor(max_workers=self.semaphore_limit) as executor:
            # Schedule all documents to run in thread pool
            futures = [
                loop.run_in_executor(
                    executor, 
                    self._process_single_document_sync, 
                    law_id
                )
                for law_id in law_ids
            ]
            
            # Wait for all to complete
            results = await asyncio.gather(*futures, return_exceptions=True)
        
        # Handle any exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                step_logger.error(f"[Worker] {law_ids[i]} exception: {result}")
                processed_results.append(DocumentResult(
                    law_id=law_ids[i],
                    success=False,
                    error_message=str(result)
                ))
            else:
                processed_results.append(result)
                
        return processed_results
    
    def _process_single_document_sync(self, law_id: str) -> DocumentResult:
        """
        Process a single document through the pipeline (SYNCHRONOUS).
        
        This runs in a thread pool worker. Uses shared adapter and
        embedding resources, but creates per-document repositories.
        Reference linking is skipped (done in bulk later).
        """
        start_time = perf_counter()
        
        try:
            # Import pipeline components
            from src.application.pipeline.data_ingestion import DataRetriever
            from src.application.pipeline.data_processing import DataProcessor
            from src.application.pipeline.embedding_step import EmbeddingGenerator
            from src.domain.repository.normativa_repository import NormativaRepository
            from src.domain.repository.change_repository import ChangeRepository
            
            step_logger.info(f"[Worker] Processing {law_id}...")
            
            # Step 1: Retrieve data from BOE API
            retriever = DataRetriever(name="retriever", search_criteria=law_id)
            raw_data = retriever.process(None)
            
            if not raw_data or not raw_data.get("data"):
                return DocumentResult(
                    law_id=law_id,
                    success=False,
                    error_message="No data retrieved from BOE API"
                )
            
            # Step 2: Process data into domain model
            processor = DataProcessor(name="processor")
            normativa, change_events = processor.process(raw_data)
            
            if not normativa:
                return DocumentResult(
                    law_id=law_id,
                    success=False,
                    error_message="Failed to process normativa"
                )
            
            # Step 3: Generate embeddings (using SHARED provider and cache)
            generator = EmbeddingGenerator(
                name="embedding_generator",
                provider=self._embedding_provider,
                cache=self._embedding_cache
            )
            generator.process((normativa, change_events))
            
            # Commit embedding cache after each document (prevents data loss + WAL growth)
            if self._embedding_cache:
                self._embedding_cache.save()
            
            # Step 4: Save to Neo4j (skip reference linking - done in bulk)
            normativa_repo = NormativaRepository(self._adapter)
            save_result = normativa_repo.save_normativa(normativa)
            
            # Save change events if any
            if change_events:
                change_repo = ChangeRepository(self._adapter)
                change_repo.save_change_events(change_events, normativa_id=save_result["doc_id"])
            
            duration = perf_counter() - start_time
            step_logger.info(
                f"[Worker] {law_id} complete: "
                f"{save_result['nodes_created']} nodes, "
                f"{save_result['relationships_created']} rels, "
                f"{duration:.2f}s"
            )
            
            return DocumentResult(
                law_id=law_id,
                success=True,
                nodes_created=save_result["nodes_created"],
                relationships_created=save_result["relationships_created"],
                articles_count=save_result.get("tree_nodes", 0),
                duration_seconds=duration
            )
            
        except Exception as e:
            step_logger.error(f"[Worker] {law_id} failed: {e}")
            return DocumentResult(
                law_id=law_id,
                success=False,
                duration_seconds=perf_counter() - start_time,
                error_message=str(e)
            )
    
    def _bulk_link_references(self) -> int:
        """
        Bulk reference linking after all documents are ingested.
        
        Processes articles in batches of 5000 to create REFERS_TO relationships.
        """
        from src.ingestion.bulk_reference_linker import BulkReferenceLinker
        
        linker = BulkReferenceLinker(self._adapter, batch_size=self.batch_size)
        total_links = linker.link_all_pending()
        
        step_logger.info(f"[Orchestrator] Created {total_links} reference links")
        return total_links
