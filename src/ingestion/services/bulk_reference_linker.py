"""
Bulk Reference Linker for Concurrent Ingestion.

Processes reference linking in large batches AFTER all documents are ingested.

Why batch after graph build?
- All target articles exist (no missing targets)
- Database is "warm" with all potential targets indexed
- Single batch of N relationships >> N single queries
- Cross-document references can be resolved
"""
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from src.domain.services.reference_extractor import (
    ReferenceExtractor,
    ExtractedReference,
    ReferenceType
)
from src.infrastructure.graphdb.adapter import Neo4jAdapter
from src.utils.logger import step_logger
from src.utils.spanish_number_converter import normalize_article_number


@dataclass
class LinkingStats:
    """Statistics from a bulk linking run."""
    articles_processed: int = 0
    references_found: int = 0
    internal_links_created: int = 0
    external_links_created: int = 0
    unresolved_references: int = 0


class BulkReferenceLinker:
    """
    Links REFERS_TO relationships in batches of articles.
    
    Designed to run AFTER the graph build phase when all documents
    are already ingested, enabling cross-document reference resolution.
    """
    
    # Relationship types based on reference context
    REL_REFERS_TO = "REFERS_TO"
    REL_DEROGATES = "DEROGATES"
    REL_MODIFIES = "MODIFIES"
    
    def __init__(
        self, 
        adapter: Neo4jAdapter, 
        batch_size: int = 5000
    ):
        self.adapter = adapter
        self.batch_size = batch_size
        self.extractor = ReferenceExtractor()
        
        # Cache for normativa existence checks
        self._normativa_cache: Dict[str, bool] = {}
    
    def link_all_pending(self, max_workers: int = 6) -> int:
        """
        Process all articles and create reference links.
        
        Uses concurrent batch processing for improved performance.
        
        Args:
            max_workers: Max concurrent batch processing threads (default: 6)
        
        Returns:
            Total number of links created
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading
        
        # Thread-safe stats
        stats_lock = threading.Lock()
        stats = LinkingStats()
        total_links = 0
        
        step_logger.info(f"[BulkLinker] Starting bulk reference linking (workers={max_workers})...")
        
        # First, fetch all batches
        all_batches = []
        offset = 0
        while True:
            articles = self._fetch_article_batch(offset)
            if not articles:
                break
            all_batches.append(articles)
            offset += self.batch_size
        
        if not all_batches:
            step_logger.info("[BulkLinker] No articles to process.")
            return 0
        
        step_logger.info(f"[BulkLinker] Fetched {len(all_batches)} batches ({sum(len(b) for b in all_batches)} articles)")
        
        # Process batches concurrently
        def process_batch_wrapper(batch_idx: int, batch: List[Dict[str, Any]]) -> int:
            """Wrapper for thread-safe batch processing."""
            local_stats = LinkingStats()
            links_created = self._process_batch(batch, local_stats)
            
            # Merge stats thread-safely
            with stats_lock:
                stats.articles_processed += local_stats.articles_processed
                stats.references_found += local_stats.references_found
                stats.internal_links_created += local_stats.internal_links_created
                stats.external_links_created += local_stats.external_links_created
                stats.unresolved_references += local_stats.unresolved_references
            
            step_logger.info(f"[BulkLinker] Batch {batch_idx + 1}/{len(all_batches)}: {len(batch)} articles, {links_created} links")
            return links_created
        
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="Linker") as executor:
            futures = {
                executor.submit(process_batch_wrapper, i, batch): i
                for i, batch in enumerate(all_batches)
            }
            
            for future in as_completed(futures):
                try:
                    links = future.result()
                    total_links += links
                except Exception as e:
                    batch_idx = futures[future]
                    step_logger.error(f"[BulkLinker] Batch {batch_idx + 1} failed: {e}")
        
        step_logger.info(
            f"[BulkLinker] Complete. "
            f"Processed {stats.articles_processed} articles, "
            f"Found {stats.references_found} references, "
            f"Created {stats.internal_links_created + stats.external_links_created} links, "
            f"Unresolved: {stats.unresolved_references}"
        )
        
        return total_links
    
    def _fetch_article_batch(self, offset: int) -> List[Dict[str, Any]]:
        """
        Fetch a batch of articles with their normativa context.
        
        Query fetches articles that have full_text and returns
        the normativa_id for context.
        """
        query = """
        MATCH (a:articulo)-[:PART_OF]->(n:Normativa)
        WHERE a.full_text IS NOT NULL
        RETURN 
            a.id as id, 
            a.full_text as full_text, 
            a.name as name,
            a.fecha_vigencia as fecha_vigencia,
            n.id as normativa_id
        ORDER BY a.id
        SKIP $offset LIMIT $batch_size
        """
        return self.adapter.run_query(query, {
            "offset": offset,
            "batch_size": self.batch_size
        })
    
    def _process_batch(
        self, 
        articles: List[Dict[str, Any]],
        stats: LinkingStats
    ) -> int:
        """
        Process a batch of articles and create reference links.
        
        Returns number of links created in this batch.
        """
        relationships_to_create: List[Dict[str, Any]] = []
        
        for article in articles:
            stats.articles_processed += 1
            
            article_id = article["id"]
            article_text = article.get("full_text", "")
            article_name = article.get("name", "")
            normativa_id = article.get("normativa_id")
            referencer_fecha = article.get("fecha_vigencia")
            
            if not article_text:
                continue
            
            # Extract current article number for relative references
            current_art_match = re.search(r'\d+', article_name or '')
            current_article_num = current_art_match.group(0) if current_art_match else None
            
            # Extract references from text
            extraction = self.extractor.extract(
                text=article_text,
                source_document_id=article_id,
                current_normativa_id=normativa_id,
                current_article_number=current_article_num
            )
            
            stats.references_found += len(extraction.references)
            stats.unresolved_references += len(extraction.unresolved_references)
            
            # Build relationships
            for ref in extraction.references:
                rel_data = self._build_reference_link(
                    article_id, 
                    ref, 
                    normativa_id, 
                    referencer_fecha
                )
                if rel_data:
                    relationships_to_create.append(rel_data)
                    if ref.is_external:
                        stats.external_links_created += 1
                    else:
                        stats.internal_links_created += 1
        
        # Batch insert all relationships
        if relationships_to_create:
            self.adapter.batch_merge_relationships(relationships_to_create)
        
        return len(relationships_to_create)
    
    def _build_reference_link(
        self,
        source_article_id: str,
        ref: ExtractedReference,
        current_normativa_id: str,
        referencer_fecha: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """
        Build relationship data dict for a single reference.
        Returns None if reference can't be resolved.
        """
        if ref.reference_type == ReferenceType.JUDICIAL:
            return None
        
        target_id = None
        target_label = None
        
        # Internal reference - look up in same normativa
        if not ref.is_external:
            if ref.article_number and ref.article_number not in ("anterior", "siguiente", "precedente"):
                clean_num = self._normalize_article_number(ref.article_number)
                target_id = self._find_article_in_normativa(
                    current_normativa_id, 
                    clean_num,
                    referencer_fecha
                )
                target_label = "articulo"
        
        # External reference
        elif ref.resolved_boe_id:
            if ref.article_number:
                clean_num = self._normalize_article_number(ref.article_number)
                target_id = self._find_article_in_normativa(
                    ref.resolved_boe_id,
                    clean_num,
                    referencer_fecha
                )
                target_label = "articulo"
            
            if not target_id:
                # Fall back to normativa itself
                if self._normativa_exists(ref.resolved_boe_id):
                    target_id = ref.resolved_boe_id
                    target_label = "Normativa"
        
        if target_id and target_label:
            rel_type = self._determine_relationship_type(ref)
            return {
                "from_id": source_article_id,
                "from_label": "articulo",
                "to_id": target_id,
                "to_label": target_label,
                "rel_type": rel_type,
                "props": {
                    "raw_citation": ref.raw_text[:200]
                }
            }
        
        return None
    
    def _normalize_article_number(self, article_number: str) -> str:
        """
        Normalize article number to match clean_number format.
        
        Now handles both numeric and Spanish written numbers.
        """
        num = article_number.strip().rstrip('º\u00aa')
        result = normalize_article_number(num)
        # Fall back to cleaned input if normalization fails
        return result if result else num
    
    def _find_article_in_normativa(
        self,
        normativa_id: str,
        clean_num: str,
        referencer_fecha: Optional[str] = None
    ) -> Optional[str]:
        """
        Find article by clean_number within a normativa.
        Uses index on clean_number for O(1) lookup.
        """
        query = """
        MATCH (a:articulo)-[:PART_OF]->(n:Normativa {id: $normativa_id})
        WHERE a.clean_number = $clean_num
          AND ($ref_fecha IS NULL 
               OR (a.fecha_vigencia IS NOT NULL 
                   AND a.fecha_vigencia <= $ref_fecha
                   AND (a.fecha_caducidad IS NULL OR $ref_fecha < a.fecha_caducidad)))
        RETURN a.id as id
        ORDER BY a.fecha_vigencia DESC
        LIMIT 1
        """
        result = self.adapter.run_query_single(query, {
            "normativa_id": normativa_id,
            "clean_num": clean_num,
            "ref_fecha": referencer_fecha
        })
        return result["id"] if result else None
    
    def _normativa_exists(self, normativa_id: str) -> bool:
        """Check if a Normativa exists (with caching)."""
        if normativa_id in self._normativa_cache:
            return self._normativa_cache[normativa_id]
        
        query = """
        MATCH (n:Normativa {id: $normativa_id})
        RETURN n.id as id
        LIMIT 1
        """
        result = self.adapter.run_query_single(query, {"normativa_id": normativa_id})
        exists = result is not None
        self._normativa_cache[normativa_id] = exists
        return exists
    
    def _determine_relationship_type(self, ref: ExtractedReference) -> str:
        """Determine the relationship type based on reference context."""
        raw_lower = ref.raw_text.lower()
        
        if "deroga" in raw_lower:
            return self.REL_DEROGATES
        elif "modifica" in raw_lower:
            return self.REL_MODIFIES
        else:
            return self.REL_REFERS_TO
