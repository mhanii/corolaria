"""
Decoupled Ingestion Orchestrator.

Refactored Producer-Consumer implementation using specialized workers
and resource management service.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Any
from time import perf_counter

from src.ingestion.config import IngestionConfig
from src.ingestion.models import (
    BatchIngestionResult, DocumentResult, ParsedDocument, EmbeddedDocument
)
from src.ingestion.services import ResourceManager, DictionaryPreloader, BulkReferenceLinker
from src.ingestion.workers import (
    parse_document_sync,
    generate_embeddings_scatter_gather,
    save_to_neo4j_sync
)
from src.utils.logger import step_logger

# Poison pill to signal worker shutdown
POISON_PILL = None


class DecoupledIngestionOrchestrator:
    """
    Orchestrates the ingestion pipeline using 3 decoupled thread pools.
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
        self.scatter_chunk_size = scatter_chunk_size
        self.skip_embeddings = skip_embeddings
        
        self.config = config or IngestionConfig.from_env()
        self.resource_manager = ResourceManager(self.config, simulate_embeddings)
        
        # Queues
        self._embed_queue: asyncio.Queue = asyncio.Queue(maxsize=queue_maxsize)
        self._save_queue: asyncio.Queue = asyncio.Queue(maxsize=queue_maxsize)
        
        # Results
        self._results: List[DocumentResult] = []
        self._results_lock = asyncio.Lock()

    async def run(self, law_ids: List[str]) -> BatchIngestionResult:
        """Execute the ingestion pipeline."""
        start_time = perf_counter()
        
        step_logger.info("Stage 0: Preparing resources...")
        await self.resource_manager.initialize()
        self.resource_manager.prepare_database()
        
        # Preload dictionary
        preloader = DictionaryPreloader(self.resource_manager.adapter)
        dictionary_stats = preloader.preload_all()
        
        step_logger.info(f"Stage 1: Launching workers (CPU={self.cpu_workers}, Network={self.network_workers}, Disk={self.disk_workers})...")
        
        # Phase timing markers
        phase_parse_start = perf_counter()
        phase_embed_start = 0.0
        phase_save_start = 0.0
        phase_parse_end = 0.0
        phase_embed_end = 0.0
        phase_save_end = 0.0
        
        with ThreadPoolExecutor(max_workers=self.cpu_workers, thread_name_prefix="CPU") as cpu_pool, \
             ThreadPoolExecutor(max_workers=self.network_workers, thread_name_prefix="Net") as network_pool, \
             ThreadPoolExecutor(max_workers=self.disk_workers, thread_name_prefix="Disk") as disk_pool:
            
            # Start consumer tasks
            cpu_tasks = [
                asyncio.create_task(self._cpu_worker_task(law_ids, cpu_pool))
            ]
            
            network_tasks = [
                asyncio.create_task(self._network_worker_task(network_pool))
                for _ in range(self.network_workers)
            ]
            
            disk_tasks = [
                asyncio.create_task(self._disk_worker_task(disk_pool))
                for _ in range(self.disk_workers)
            ]
            
            # Wait for CPU (producers)
            await asyncio.gather(*cpu_tasks)
            phase_parse_end = perf_counter()
            phase_embed_start = phase_parse_end  # Embed phase starts when parse ends
            step_logger.info("[Decoupled] CPU workers complete. Sending poison pills to network workers...")
            
            # Signal Network workers to stop
            for _ in range(self.network_workers):
                await self._embed_queue.put(POISON_PILL)
            await asyncio.gather(*network_tasks)
            phase_embed_end = perf_counter()
            phase_save_start = phase_embed_end  # Save phase starts when embed ends
            step_logger.info("[Decoupled] Network workers complete. Sending poison pills to disk workers...")
            
            # Signal Disk workers to stop
            for _ in range(self.disk_workers):
                await self._save_queue.put(POISON_PILL)
            await asyncio.gather(*disk_tasks)
            phase_save_end = perf_counter()
            step_logger.info("[Decoupled] Disk workers complete.")
            
        step_logger.info("Stage 2: Processing complete. Creating vector index...")
        self.resource_manager.create_vector_index()
        
        link_duration = 0.0
        if not self.skip_embeddings:
            step_logger.info("Stage 3: Linking references...")
            link_start = perf_counter()
            linker = BulkReferenceLinker(self.resource_manager.adapter)
            linker.link_all_pending()
            link_duration = perf_counter() - link_start
        
        duration = perf_counter() - start_time
        successful = sum(1 for r in self._results if r.success)
        failed = sum(1 for r in self._results if not r.success)
        
        # Aggregate stage timings (sum of per-doc times)
        total_parse = sum(r.parse_duration for r in self._results)
        total_embed = sum(r.embed_duration for r in self._results)
        total_save = sum(r.save_duration for r in self._results)
        
        # Wall-clock phase durations
        phase_parse = phase_parse_end - phase_parse_start
        phase_embed = phase_embed_end - phase_embed_start if phase_embed_start > 0 else 0.0
        phase_save = phase_save_end - phase_save_start if phase_save_start > 0 else 0.0
        
        self.resource_manager.close()
        
        return BatchIngestionResult(
            total_documents=len(law_ids),
            successful=successful,
            failed=failed,
            total_nodes=sum(r.nodes_created for r in self._results),
            total_relationships=sum(r.relationships_created for r in self._results),
            total_reference_links=0,  # Updated by linker if run
            duration_seconds=duration,
            total_parse_duration=total_parse,
            total_embed_duration=total_embed,
            total_save_duration=total_save,
            link_duration=link_duration,
            phase_parse_duration=phase_parse,
            phase_embed_duration=phase_embed,
            phase_save_duration=phase_save,
            document_results=self._results,
            dictionary_stats=dictionary_stats
        )

    # --- Worker Tasks ---

    async def _cpu_worker_task(self, law_ids: List[str], pool: ThreadPoolExecutor):
        """Producer: Fetches documents and feeds embed_queue."""
        loop = asyncio.get_running_loop()
        
        for law_id in law_ids:
            try:
                # Use functools.partial to pass the flag
                from functools import partial
                parse_fn = partial(parse_document_sync, enable_table_parsing=self.config.enable_table_parsing)
                parsed = await loop.run_in_executor(
                    pool,
                    parse_fn,
                    law_id
                )
                
                if parsed:
                    await self._embed_queue.put(parsed)
                    step_logger.info(f"[CPU] {law_id} parsed ({parsed.parse_duration:.2f}s)")
                else:
                    async with self._results_lock:
                        self._results.append(DocumentResult(
                            law_id=law_id, success=False, error_message="Parse failed"
                        ))
            except Exception as e:
                step_logger.error(f"[CPU] {law_id} failed: {e}")
                async with self._results_lock:
                    self._results.append(DocumentResult(
                        law_id=law_id, success=False, error_message=str(e)
                    ))

    async def _network_worker_task(self, pool: ThreadPoolExecutor):
        """Consumer: Embeds documents and feeds save_queue."""
        loop = asyncio.get_running_loop()
        while True:
            parsed = await self._embed_queue.get()
            if parsed is POISON_PILL:
                self._embed_queue.task_done()
                break
                
            try:
                # --skip-embeddings Logic
                if self.skip_embeddings:
                    embedded = EmbeddedDocument(
                        law_id=parsed.law_id,
                        normativa=parsed.normativa,
                        change_events=parsed.change_events,
                        parse_duration=parsed.parse_duration,
                        embed_duration=0.0
                    )
                    await self._save_queue.put(embedded)
                    step_logger.info(f"[Network] {parsed.law_id} skipped embeddings")
                    continue
                
                # Normal Embedding Logic
                embedded = await generate_embeddings_scatter_gather(
                    parsed,
                    self.resource_manager.embedding_provider,
                    self.resource_manager.embedding_cache,
                    pool,
                    self.scatter_chunk_size
                )
                
                await self._save_queue.put(embedded)
                step_logger.info(f"[Network] {parsed.law_id} embedded ({embedded.embed_duration:.2f}s)")
                
            except Exception as e:
                step_logger.error(f"[Network] {parsed.law_id} failed: {e}")
                async with self._results_lock:
                    self._results.append(DocumentResult(
                        law_id=parsed.law_id, success=False, error_message=str(e)
                    ))
            finally:
                self._embed_queue.task_done()

    async def _disk_worker_task(self, pool: ThreadPoolExecutor):
        """Consumer: Saves documents to Neo4j."""
        loop = asyncio.get_running_loop()
        
        while True:
            embedded = await self._save_queue.get()
            if embedded is POISON_PILL:
                self._save_queue.task_done()
                break
                
            try:
                result = await loop.run_in_executor(
                    pool,
                    save_to_neo4j_sync,
                    embedded,
                    self.resource_manager.adapter
                )
                
                async with self._results_lock:
                    self._results.append(result)
                
                step_logger.info(f"[Disk] {embedded.law_id} saved ({result.duration_seconds:.2f}s)")
                
            except Exception as e:
                step_logger.error(f"[Disk] {embedded.law_id} failed: {e}")
                async with self._results_lock:
                    self._results.append(DocumentResult(
                        law_id=embedded.law_id, success=False, error_message=str(e)
                    ))
            finally:
                self._save_queue.task_done()
