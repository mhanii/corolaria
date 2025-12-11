"""
Decoupled Ingestion Orchestrator - Producer-Consumer Pattern.

Uses 3 separate thread pools connected by asyncio queues to maximize CPU
saturation during I/O waits:

1. CPU Pool (Parsers):    Fetch + Parse XML → push to embed_queue
2. Network Pool (Embedders): Generate embeddings → push to save_queue  
3. Disk Pool (Writers):    Write to Neo4j

This architecture decouples CPU-bound parsing from network-bound API calls
from disk-bound database writes, enabling maximum parallelism.

Usage:
    orchestrator = DecoupledIngestionOrchestrator(
        cpu_workers=5,
        network_workers=20,
        disk_workers=2,
        simulate_embeddings=True  # For stress testing
    )
    result = await orchestrator.run(law_ids)
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from time import perf_counter
from typing import List, Optional, Dict, Any, Tuple

from src.infrastructure.graphdb.connection import Neo4jConnection
from src.infrastructure.graphdb.adapter import Neo4jAdapter
from src.ai.embeddings.factory import EmbeddingFactory
from src.ai.embeddings.sqlite_cache import SQLiteEmbeddingCache
from src.ai.indexing.factory import IndexerFactory
from src.domain.value_objects.embedding_config import EmbeddingConfig
from src.domain.models.normativa import NormativaCons
from src.utils.logger import step_logger

from .dictionary_preloader import DictionaryPreloader
from .config import IngestionConfig


# Poison pill to signal worker shutdown
POISON_PILL = None


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


@dataclass
class ParsedDocument:
    """Document after CPU parsing phase."""
    law_id: str
    normativa: NormativaCons
    change_events: List[Any]
    parse_duration: float


@dataclass
class EmbeddedDocument:
    """Document after embedding phase."""
    law_id: str
    normativa: NormativaCons
    change_events: List[Any]
    parse_duration: float
    embed_duration: float


class DecoupledIngestionOrchestrator:
    """
    Producer-Consumer orchestrator with 3 decoupled thread pools.
    
    Architecture:
    ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
    │  CPU Pool   │ --> │ embed_queue │ --> │ Network Pool│
    │  (Parsers)  │     │  (maxsize=50)│     │ (Embedders) │
    └─────────────┘     └─────────────┘     └─────────────┘
                                                   │
                                                   v
                        ┌─────────────┐     ┌─────────────┐
                        │  Disk Pool  │ <-- │ save_queue  │
                        │  (Writers)  │     │ (maxsize=50)│
                        └─────────────┘     └─────────────┘
    """
    
    def __init__(
        self,
        cpu_workers: int = 5,
        network_workers: int = 20,
        disk_workers: int = 2,
        queue_maxsize: int = 50,
        scatter_chunk_size: int = 500,
        skip_embeddings: bool = False,
        simulate_embeddings: bool = False,
        config: Optional[IngestionConfig] = None
    ):
        self.cpu_workers = cpu_workers
        self.network_workers = network_workers
        self.disk_workers = disk_workers
        self.queue_maxsize = queue_maxsize
        self.scatter_chunk_size = scatter_chunk_size  # Articles per chunk for scatter-gather
        self.skip_embeddings = skip_embeddings  # Skip embedding generation entirely
        self.simulate_embeddings = simulate_embeddings
        self.config = config or IngestionConfig.from_env()
        
        # Embedding configuration
        self.embedding_config = EmbeddingConfig(
            model_name="models/gemini-embedding-001",
            dimensions=768,
            similarity="cosine",
            task_type="RETRIEVAL_DOCUMENT"
        )
        
        # Shared resources (initialized in run())
        self._connection: Optional[Neo4jConnection] = None
        self._adapter: Optional[Neo4jAdapter] = None
        self._indexer = None
        self._embedding_cache: Optional[SQLiteEmbeddingCache] = None
        self._embedding_provider = None
        
        # Queues (initialized in run())
        self._embed_queue: Optional[asyncio.Queue] = None
        self._save_queue: Optional[asyncio.Queue] = None
        
        # Results tracking (thread-safe via list append)
        self._results: List[DocumentResult] = []
        self._results_lock = asyncio.Lock()
        
    async def run(self, law_ids: List[str]) -> BatchIngestionResult:
        """
        Execute the decoupled producer-consumer ingestion pipeline.
        """
        start_time = perf_counter()
        result = BatchIngestionResult(total_documents=len(law_ids))
        
        step_logger.info(f"[Decoupled] Starting ingestion of {len(law_ids)} documents")
        step_logger.info(f"[Decoupled] Workers: CPU={self.cpu_workers}, Network={self.network_workers}, Disk={self.disk_workers}")
        step_logger.info(f"[Decoupled] Simulation mode: {self.simulate_embeddings}")
        
        try:
            # Initialize shared resources
            await self._initialize_resources()
            
            # Stage 0: Drop vector index + preload dictionaries
            step_logger.info("[Decoupled] Stage 0: Preparing database...")
            self._indexer.drop_index()
            preloader = DictionaryPreloader(self._adapter)
            result.dictionary_stats = preloader.preload_all()
            
            # Initialize queues
            self._embed_queue = asyncio.Queue(maxsize=self.queue_maxsize)
            self._save_queue = asyncio.Queue(maxsize=self.queue_maxsize)
            self._results = []
            
            # Create thread pools
            cpu_pool = ThreadPoolExecutor(max_workers=self.cpu_workers, thread_name_prefix="cpu")
            network_pool = ThreadPoolExecutor(max_workers=self.network_workers, thread_name_prefix="network")
            disk_pool = ThreadPoolExecutor(max_workers=self.disk_workers, thread_name_prefix="disk")
            
            try:
                # Stage 1: Start all worker pools
                step_logger.info("[Decoupled] Stage 1: Starting worker pools...")
                
                # Start CPU workers (producers)
                cpu_tasks = [
                    asyncio.create_task(self._cpu_worker(law_id, cpu_pool))
                    for law_id in law_ids
                ]
                
                # Start Network workers (consumers/producers) 
                network_tasks = [
                    asyncio.create_task(self._network_worker(network_pool))
                    for _ in range(self.network_workers)
                ]
                
                # Start Disk workers (consumers)
                disk_tasks = [
                    asyncio.create_task(self._disk_worker(disk_pool))
                    for _ in range(self.disk_workers)
                ]
                
                # Wait for all CPU workers to complete
                await asyncio.gather(*cpu_tasks)
                step_logger.info("[Decoupled] All CPU workers complete, sending poison pills to embed_queue...")
                
                # Send poison pills to network workers
                for _ in range(self.network_workers):
                    await self._embed_queue.put(POISON_PILL)
                
                # Wait for network workers to complete
                await asyncio.gather(*network_tasks)
                step_logger.info("[Decoupled] All Network workers complete, sending poison pills to save_queue...")
                
                # Send poison pills to disk workers
                for _ in range(self.disk_workers):
                    await self._save_queue.put(POISON_PILL)
                
                # Wait for disk workers to complete
                await asyncio.gather(*disk_tasks)
                step_logger.info("[Decoupled] All Disk workers complete")
                
            finally:
                cpu_pool.shutdown(wait=True)
                network_pool.shutdown(wait=True)
                disk_pool.shutdown(wait=True)
            
            # Stage 2: Bulk reference linking
            step_logger.info("[Decoupled] Stage 2: Bulk reference linking...")
            result.total_reference_links = self._bulk_link_references()
            
            # Stage 3: Rebuild vector index
            step_logger.info("[Decoupled] Stage 3: Creating vector index...")
            self._indexer.create_index()
            
            # Calculate final stats
            result.document_results = self._results
            for doc_result in self._results:
                if doc_result.success:
                    result.successful += 1
                    result.total_nodes += doc_result.nodes_created
                    result.total_relationships += doc_result.relationships_created
                else:
                    result.failed += 1
            
            result.duration_seconds = perf_counter() - start_time
            step_logger.info(
                f"[Decoupled] Complete. "
                f"{result.successful}/{result.total_documents} successful, "
                f"{result.total_nodes} nodes, "
                f"{result.total_reference_links} reference links, "
                f"{result.duration_seconds:.2f}s"
            )
            
        finally:
            if self._connection:
                self._connection.close()
                
        return result
    
    async def _initialize_resources(self):
        """Initialize shared resources."""
        # Neo4j connection
        self._connection = Neo4jConnection(
            self.config.neo4j.uri,
            self.config.neo4j.user,
            self.config.neo4j.password
        )
        self._adapter = Neo4jAdapter(self._connection)
        self._adapter.ensure_constraints()
        
        # Embedding cache (shared across all workers)
        self._embedding_cache = SQLiteEmbeddingCache("data/embeddings_cache.db")
        
        # Embedding provider (with optional simulation)
        self._embedding_provider = EmbeddingFactory.create(
            provider="gemini",
            model=self.embedding_config.model_name,
            dimensions=self.embedding_config.dimensions,
            task_type=self.embedding_config.task_type,
            simulate=self.simulate_embeddings
        )
        
        # Indexer
        self._indexer = IndexerFactory.create(
            "neo4j",
            self.embedding_config,
            adapter=self._adapter
        )
    
    async def _cpu_worker(self, law_id: str, pool: ThreadPoolExecutor):
        """
        CPU Worker: Fetch and parse a document, then push to embed_queue.
        """
        loop = asyncio.get_running_loop()
        
        try:
            parsed = await loop.run_in_executor(pool, self._parse_document_sync, law_id)
            
            if parsed:
                await self._embed_queue.put(parsed)
                step_logger.info(f"[CPU] {law_id} parsed and queued ({parsed.parse_duration:.2f}s)")
            else:
                # Failed to parse - record result immediately
                async with self._results_lock:
                    self._results.append(DocumentResult(
                        law_id=law_id,
                        success=False,
                        error_message="Failed to parse document"
                    ))
                    
        except Exception as e:
            step_logger.error(f"[CPU] {law_id} failed: {e}")
            async with self._results_lock:
                self._results.append(DocumentResult(
                    law_id=law_id,
                    success=False,
                    error_message=str(e)
                ))
    
    def _parse_document_sync(self, law_id: str) -> Optional[ParsedDocument]:
        """
        Synchronous document parsing (runs in CPU thread pool).
        """
        start_time = perf_counter()
        
        from src.application.pipeline.data_ingestion import DataRetriever
        from src.application.pipeline.data_processing import DataProcessor
        
        # Fetch from API
        retriever = DataRetriever(name="retriever", search_criteria=law_id)
        raw_data = retriever.process(None)
        
        if not raw_data or not raw_data.get("data"):
            return None
        
        # Parse to domain model
        processor = DataProcessor(name="processor")
        normativa, change_events = processor.process(raw_data)
        
        if not normativa:
            return None
        
        return ParsedDocument(
            law_id=law_id,
            normativa=normativa,
            change_events=change_events or [],
            parse_duration=perf_counter() - start_time
        )
    
    async def _network_worker(self, pool: ThreadPoolExecutor):
        """
        Network Worker: Generate embeddings for documents from embed_queue,
        then push to save_queue.
        
        Uses SCATTER-GATHER pattern for large documents:
        - Scatter: Split document articles into chunks
        - Parallel: Process chunks concurrently in thread pool  
        - Gather: Wait for all chunks, articles updated by reference
        """
        loop = asyncio.get_running_loop()
        
        while True:
            # Get next document from queue
            parsed = await self._embed_queue.get()
            
            # Check for poison pill
            if parsed is POISON_PILL:
                self._embed_queue.task_done()
                break
            
            try:
                start_time = perf_counter()
                
                # SKIP EMBEDDINGS MODE: Pass directly to save_queue
                if self.skip_embeddings:
                    embedded = EmbeddedDocument(
                        law_id=parsed.law_id,
                        normativa=parsed.normativa,
                        change_events=parsed.change_events,
                        parse_duration=parsed.parse_duration,
                        embed_duration=0.0
                    )
                    await self._save_queue.put(embedded)
                    step_logger.info(f"[Network] {parsed.law_id} skipped embeddings, queued ({perf_counter() - start_time:.2f}s)")
                    self._embed_queue.task_done()
                    continue
                
                # Import here to avoid circular imports
                from src.application.pipeline.embedding_step import EmbeddingGenerator
                
                # Create generator (uses shared cache and provider)
                generator = EmbeddingGenerator(
                    name="embedding_generator",
                    provider=self._embedding_provider,
                    cache=self._embedding_cache
                )
                
                # Collect all articles from the document tree
                articles = generator.collect_articles(parsed.normativa.content_tree)
                
                if not articles:
                    # No articles, just pass through
                    embedded = EmbeddedDocument(
                        law_id=parsed.law_id,
                        normativa=parsed.normativa,
                        change_events=parsed.change_events,
                        parse_duration=parsed.parse_duration,
                        embed_duration=0.0
                    )
                    await self._save_queue.put(embedded)
                    step_logger.info(f"[Network] {parsed.law_id} no articles, queued")
                    self._embed_queue.task_done()
                    continue
                
                # Determine if we need scatter-gather
                if len(articles) <= self.scatter_chunk_size:
                    # Small document - process directly
                    embeddings_count = await loop.run_in_executor(
                        pool,
                        generator.process_subset,
                        articles,
                        parsed.normativa,
                        0,
                        1
                    )
                else:
                    # Large document - SCATTER-GATHER
                    chunks = [
                        articles[i:i + self.scatter_chunk_size]
                        for i in range(0, len(articles), self.scatter_chunk_size)
                    ]
                    total_chunks = len(chunks)
                    
                    step_logger.info(
                        f"[Network] {parsed.law_id}: Scatter-Gather {len(articles)} articles "
                        f"into {total_chunks} chunks of ~{self.scatter_chunk_size}"
                    )
                    
                    # Schedule all chunks to run in parallel
                    chunk_tasks = [
                        loop.run_in_executor(
                            pool,
                            generator.process_subset,
                            chunk,
                            parsed.normativa,
                            i,
                            total_chunks
                        )
                        for i, chunk in enumerate(chunks)
                    ]
                    
                    # Gather results (articles updated by reference)
                    chunk_results = await asyncio.gather(*chunk_tasks, return_exceptions=True)
                    
                    # Check for errors
                    for i, result in enumerate(chunk_results):
                        if isinstance(result, Exception):
                            raise RuntimeError(f"Chunk {i+1}/{total_chunks} failed: {result}")
                    
                    embeddings_count = sum(chunk_results)
                
                # Commit cache after document
                if self._embedding_cache:
                    self._embedding_cache.save()
                
                embed_duration = perf_counter() - start_time
                
                embedded = EmbeddedDocument(
                    law_id=parsed.law_id,
                    normativa=parsed.normativa,
                    change_events=parsed.change_events,
                    parse_duration=parsed.parse_duration,
                    embed_duration=embed_duration
                )
                
                await self._save_queue.put(embedded)
                step_logger.info(f"[Network] {parsed.law_id} embedded and queued ({embed_duration:.2f}s)")
                
            except Exception as e:
                step_logger.error(f"[Network] {parsed.law_id} failed: {e}")
                async with self._results_lock:
                    self._results.append(DocumentResult(
                        law_id=parsed.law_id,
                        success=False,
                        error_message=f"Embedding failed: {e}"
                    ))
            
            self._embed_queue.task_done()
    
    def _generate_embeddings_sync(self, parsed: ParsedDocument) -> EmbeddedDocument:
        """
        DEPRECATED: Kept for backward compatibility.
        Use _network_worker with scatter-gather instead.
        """
        start_time = perf_counter()
        
        from src.application.pipeline.embedding_step import EmbeddingGenerator
        
        generator = EmbeddingGenerator(
            name="embedding_generator",
            provider=self._embedding_provider,
            cache=self._embedding_cache
        )
        generator.process((parsed.normativa, parsed.change_events))
        
        # Commit cache after each document
        if self._embedding_cache:
            self._embedding_cache.save()
        
        return EmbeddedDocument(
            law_id=parsed.law_id,
            normativa=parsed.normativa,
            change_events=parsed.change_events,
            parse_duration=parsed.parse_duration,
            embed_duration=perf_counter() - start_time
        )
    
    async def _disk_worker(self, pool: ThreadPoolExecutor):
        """
        Disk Worker: Write documents from save_queue to Neo4j.
        """
        loop = asyncio.get_running_loop()
        
        while True:
            # Get next document from queue
            embedded = await self._save_queue.get()
            
            # Check for poison pill
            if embedded is POISON_PILL:
                self._save_queue.task_done()
                break
            
            try:
                doc_result = await loop.run_in_executor(
                    pool,
                    self._save_to_neo4j_sync,
                    embedded
                )
                
                async with self._results_lock:
                    self._results.append(doc_result)
                
                step_logger.info(
                    f"[Disk] {embedded.law_id} saved: "
                    f"{doc_result.nodes_created} nodes ({doc_result.duration_seconds:.2f}s)"
                )
                
            except Exception as e:
                step_logger.error(f"[Disk] {embedded.law_id} failed: {e}")
                async with self._results_lock:
                    self._results.append(DocumentResult(
                        law_id=embedded.law_id,
                        success=False,
                        error_message=f"Save failed: {e}"
                    ))
            
            self._save_queue.task_done()
    
    def _save_to_neo4j_sync(self, embedded: EmbeddedDocument) -> DocumentResult:
        """
        Synchronous Neo4j save (runs in Disk thread pool).
        """
        start_time = perf_counter()
        
        from src.domain.repository.normativa_repository import NormativaRepository
        from src.domain.repository.change_repository import ChangeRepository
        
        normativa_repo = NormativaRepository(self._adapter)
        save_result = normativa_repo.save_normativa(embedded.normativa)
        
        if embedded.change_events:
            change_repo = ChangeRepository(self._adapter)
            change_repo.save_change_events(embedded.change_events, normativa_id=save_result["doc_id"])
        
        total_duration = embedded.parse_duration + embedded.embed_duration + (perf_counter() - start_time)
        
        return DocumentResult(
            law_id=embedded.law_id,
            success=True,
            nodes_created=save_result["nodes_created"],
            relationships_created=save_result["relationships_created"],
            articles_count=save_result.get("tree_nodes", 0),
            duration_seconds=total_duration
        )
    
    def _bulk_link_references(self) -> int:
        """Bulk reference linking after all documents saved."""
        from src.ingestion.bulk_reference_linker import BulkReferenceLinker
        
        linker = BulkReferenceLinker(self._adapter, batch_size=5000)
        total_links = linker.link_all_pending()
        
        step_logger.info(f"[Decoupled] Created {total_links} reference links")
        return total_links
