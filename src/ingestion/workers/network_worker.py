"""
Network Worker - Embedding Generation.

Handles the network-bound embedding phase using scatter-gather pattern.
"""
from time import perf_counter
from typing import List, Optional
import asyncio
from concurrent.futures import ThreadPoolExecutor

from src.ingestion.models import ParsedDocument, EmbeddedDocument
from src.utils.logger import step_logger


def generate_embeddings_for_document(
    parsed: ParsedDocument,
    embedding_provider,
    embedding_cache,
    scatter_chunk_size: int = 500
) -> EmbeddedDocument:
    """
    Generate embeddings for all articles in a document.
    
    Uses scatter-gather pattern for large documents:
    - Split articles into chunks
    - Process chunks in parallel
    - Gather results (articles updated by reference)
    
    Args:
        parsed: Parsed document with normativa
        embedding_provider: Provider for generating embeddings
        embedding_cache: Cache for storing embeddings
        scatter_chunk_size: Max articles per chunk
        
    Returns:
        EmbeddedDocument with embeddings populated
    """
    start_time = perf_counter()
    
    from src.application.pipeline.embedding_step import EmbeddingGenerator
    
    generator = EmbeddingGenerator(
        name="embedding_generator",
        provider=embedding_provider,
        cache=embedding_cache
    )
    
    # Collect all articles
    articles = generator.collect_articles(parsed.normativa.content_tree)
    
    if not articles:
        return EmbeddedDocument(
            law_id=parsed.law_id,
            normativa=parsed.normativa,
            change_events=parsed.change_events,
            parse_duration=parsed.parse_duration,
            embed_duration=0.0
        )
    
    # Process articles (single batch for sync processing)
    generator.process_subset(
        articles=articles,
        normativa=parsed.normativa,
        chunk_id=0,
        total_chunks=1
    )
    
    # Commit cache
    if embedding_cache:
        embedding_cache.save()
    
    return EmbeddedDocument(
        law_id=parsed.law_id,
        normativa=parsed.normativa,
        change_events=parsed.change_events,
        parse_duration=parsed.parse_duration,
        embed_duration=perf_counter() - start_time
    )


async def generate_embeddings_scatter_gather(
    parsed: ParsedDocument,
    embedding_provider,
    embedding_cache,
    pool: ThreadPoolExecutor,
    scatter_chunk_size: int = 500
) -> EmbeddedDocument:
    """
    Generate embeddings using scatter-gather for parallelism.
    
    Splits large documents into chunks and processes them in parallel.
    
    Args:
        parsed: Parsed document with normativa
        embedding_provider: Provider for generating embeddings
        embedding_cache: Cache for storing embeddings
        pool: ThreadPoolExecutor for parallel processing
        scatter_chunk_size: Max articles per chunk
        
    Returns:
        EmbeddedDocument with embeddings populated
    """
    start_time = perf_counter()
    loop = asyncio.get_running_loop()
    
    from src.application.pipeline.embedding_step import EmbeddingGenerator
    
    generator = EmbeddingGenerator(
        name="embedding_generator",
        provider=embedding_provider,
        cache=embedding_cache
    )
    
    # Debug: verify cache is available
    if embedding_cache:
        step_logger.debug(f"[Network] Cache available: {type(embedding_cache).__name__}")
    else:
        step_logger.warning(f"[Network] No cache provided - embeddings will not be cached!")
    
    # Collect all articles
    articles = generator.collect_articles(parsed.normativa.content_tree)
    
    if not articles:
        return EmbeddedDocument(
            law_id=parsed.law_id,
            normativa=parsed.normativa,
            change_events=parsed.change_events,
            parse_duration=parsed.parse_duration,
            embed_duration=0.0
        )
    
    # Determine if we need scatter-gather
    if len(articles) <= scatter_chunk_size:
        # Small document - process directly
        await loop.run_in_executor(
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
            articles[i:i + scatter_chunk_size]
            for i in range(0, len(articles), scatter_chunk_size)
        ]
        total_chunks = len(chunks)
        
        step_logger.info(
            f"[Network] {parsed.law_id}: Scatter-Gather {len(articles)} articles "
            f"into {total_chunks} chunks of ~{scatter_chunk_size}"
        )
        
        # Schedule all chunks in parallel
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
        
        # Gather results
        chunk_results = await asyncio.gather(*chunk_tasks, return_exceptions=True)
        
        # Check for errors
        for i, result in enumerate(chunk_results):
            if isinstance(result, Exception):
                raise RuntimeError(f"Chunk {i+1}/{total_chunks} failed: {result}")
    
    # Commit cache
    if embedding_cache:
        embedding_cache.save()
    
    return EmbeddedDocument(
        law_id=parsed.law_id,
        normativa=parsed.normativa,
        change_events=parsed.change_events,
        parse_duration=parsed.parse_duration,
        embed_duration=perf_counter() - start_time
    )
