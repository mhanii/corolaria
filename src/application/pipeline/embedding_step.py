"""
Embedding Generator Step.

Generates embeddings for all articles in a Normativa document.

Optimized for cold-start performance using "Phased Processing" pattern:
- Phase 1: CPU-bound work (collect articles, compute hashes)
- Phase 2: Single batch I/O (cache lookup)
- Phase 3: Batched API calls (safe batch size to avoid payload limits)
- Phase 4: Single batch I/O (cache write)
"""
from typing import List, Optional, Tuple, Dict
import hashlib
from src.application.pipeline.base import Step
from src.domain.models.normativa import NormativaCons
from src.domain.models.common.node import Node, NodeType, ArticleNode
from src.domain.interfaces.embedding_provider import EmbeddingProvider
from src.domain.interfaces.embedding_cache import EmbeddingCache
from src.domain.services.article_text_builder import ArticleTextBuilder
from src.utils.logger import step_logger, output_logger


class EmbeddingGenerator(Step):
    """
    Generates embeddings for all articles in a Normativa.
    
    Uses "Phased Processing" pattern to minimize lock contention:
    - Batch cache lookups instead of N individual queries
    - Batch API calls with safe payload sizes
    - Batch cache writes instead of M individual inserts
    """
    
    def __init__(
        self, 
        name: str, 
        provider: EmbeddingProvider, 
        cache: Optional[EmbeddingCache] = None
    ):
        super().__init__(name)
        self.provider = provider
        self.cache = cache
        self.text_builder = ArticleTextBuilder()
        
        # Import tracing (optional)
        try:
            from opentelemetry import trace
            self._tracer = trace.get_tracer("embedding_generator")
            self._trace = trace
        except ImportError:
            self._tracer = None
            self._trace = None

    def process(self, data):
        """
        Process the Normativa document and generate embeddings for all articles.
        Uses phased processing for optimal performance with concurrent threads.
        """
        normativa, change_events = data
        
        if not normativa:
            step_logger.warning("Normativa is empty, skipping embedding generation.")
            return data

        # Check if provider supports simulation mode
        is_simulation = getattr(self.provider, 'simulate', False)
        mode_str = "SIMULATION" if is_simulation else "API"
        step_logger.info(f"Generating embeddings using {self.provider.model} (mode: {mode_str})")
        
        # Add tracing input attributes
        if self._tracer:
            current_span = self._trace.get_current_span()
            if current_span and current_span.is_recording():
                current_span.set_attribute("embedding.model", self.provider.model)
                current_span.set_attribute("embedding.normativa_id", normativa.id)
        
        # ========== PHASE 1: CPU Work (Collect & Hash) ==========
        # No I/O, no locks - pure computation
        articles = self._collect_articles(normativa.content_tree)
        step_logger.info(f"Found {len(articles)} articles to embed.")

        if not articles:
            return data

        # Build context text and compute hashes for ALL articles upfront
        article_data: List[Tuple[ArticleNode, str, str]] = []  # (article, text, hash)
        for article in articles:
            context_text = self.text_builder.build_context_string(normativa, article)
            context_hash = hashlib.sha256(context_text.encode('utf-8')).hexdigest()
            article_data.append((article, context_text, context_hash))
            output_logger.info(f"\n--- [EmbeddingGenerator] Processing Article {article.id} ---\n{context_text}\n")
        
        # ========== PHASE 2: Batch Cache Lookup ==========
        # Single lock acquisition for ALL cache reads
        # NOTE: In simulation mode, skip cache to stress test full pipeline
        cache_hits = 0
        to_embed: List[Tuple[ArticleNode, str, str]] = []  # (article, text, hash)
        
        if is_simulation:
            # Simulation mode: bypass cache, generate all embeddings
            to_embed = article_data
            step_logger.info(f"SIMULATION: Bypassing cache, generating {len(to_embed)} fake embeddings...")
        elif self.cache:
            all_hashes = [h for _, _, h in article_data]
            
            # Use batch lookup if available (minimizes lock contention)
            if hasattr(self.cache, 'get_batch'):
                cached_embeddings = self.cache.get_batch(all_hashes)
            else:
                # Fallback to individual lookups
                cached_embeddings = {h: self.cache.get(h) for h in all_hashes}
                cached_embeddings = {k: v for k, v in cached_embeddings.items() if v is not None}
            
            # Separate hits from misses
            for article, text, hash_key in article_data:
                if hash_key in cached_embeddings:
                    article.embedding = cached_embeddings[hash_key]
                    cache_hits += 1
                else:
                    to_embed.append((article, text, hash_key))
            
            if cache_hits == len(articles):
                step_logger.info(f"Cache: {cache_hits}/{len(articles)} articles (100% cache hit - no API calls needed)")
            elif cache_hits > 0:
                step_logger.info(f"Cache: {cache_hits}/{len(articles)} hits. Generating {len(to_embed)} new embeddings...")
            else:
                step_logger.info(f"Cache: 0 hits. Generating ALL {len(to_embed)} embeddings (cold start)...")
        else:
            to_embed = article_data
            step_logger.info(f"No cache configured. Generating ALL {len(to_embed)} embeddings...")
        
        # ========== PHASE 3: API Calls ==========
        # Provider handles batching internally - send all texts at once
        embeddings_generated = 0
        new_embeddings: Dict[str, List[float]] = {}  # hash -> embedding
        
        if to_embed:
            try:
                all_texts = [text for _, text, _ in to_embed]
                
                # Provider handles batching and logs progress
                all_embeddings = self.provider.get_embeddings(all_texts)
                embeddings_generated = len(all_embeddings)
                
                # Assign embeddings to articles and collect for cache (if not simulating)
                for (article, text, hash_key), embedding in zip(to_embed, all_embeddings):
                    article.embedding = embedding
                    if not is_simulation:
                        new_embeddings[hash_key] = embedding
                
                step_logger.info(f"✓ Assigned {embeddings_generated} embeddings to articles")
                    
            except Exception as e:
                step_logger.error(f"Error generating embeddings: {e}")
                # Continue with partial results - articles without embeddings will have None
        
        # ========== PHASE 4: Batch Cache Write ==========
        # Single lock acquisition for ALL cache writes
        # NOTE: Skip cache writes in simulation mode (fake embeddings)
        if self.cache and new_embeddings and not is_simulation:
            if hasattr(self.cache, 'set_batch'):
                self.cache.set_batch(new_embeddings)
            else:
                # Fallback to individual writes
                for hash_key, embedding in new_embeddings.items():
                    self.cache.set(hash_key, embedding)
            
            # Note: Commit is handled by caller (orchestrator) per-document

        # Add tracing output attributes
        if self._tracer:
            current_span = self._trace.get_current_span()
            if current_span and current_span.is_recording():
                current_span.set_attribute("embedding.total_articles", len(articles))
                current_span.set_attribute("embedding.cache_hits", cache_hits)
                current_span.set_attribute("embedding.embeddings_generated", embeddings_generated)
                current_span.set_attribute("embedding.cache_hit_rate", f"{cache_hits/len(articles)*100:.1f}%" if articles else "N/A")

        return data

    def _collect_articles(self, node: Node) -> List[ArticleNode]:
        """Recursively find all ArticleNodes in the tree."""
        articles = []
        if isinstance(node, ArticleNode):
            articles.append(node)
        
        if node.content:
            for child in node.content:
                if isinstance(child, Node):  # Ensure it's a Node (not string)
                    articles.extend(self._collect_articles(child))
        
        return articles
