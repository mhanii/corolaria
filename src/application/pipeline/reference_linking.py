"""
Legal Reference Linker Pipeline Step.

Extracts legal references from article text and creates REFERS_TO relationships
in the graph between articles and referenced laws/articles.

OPTIMIZED: Uses batch writes and caching to avoid N+1 query problem.
"""
import logging
import re
from functools import lru_cache
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field

from .base import Step
from .graph_construction import GraphConstructionResult
from src.domain.services.reference_extractor import (
    ReferenceExtractor, 
    ExtractedReference,
    ExtractionResult,
    ReferenceType
)
from src.infrastructure.graphdb.adapter import Neo4jAdapter

# Import tracing (optional)
try:
    from opentelemetry import trace
    _tracer = trace.get_tracer("legal_reference_linker")
except ImportError:
    _tracer = None

logger = logging.getLogger(__name__)


@dataclass
class ReferenceLinkingResult:
    """Result of reference linking step."""
    doc_id: str
    articles_processed: int = 0
    references_found: int = 0
    internal_links_created: int = 0
    external_links_created: int = 0
    unresolved_references: int = 0
    errors: List[str] = field(default_factory=list)
    
    def __repr__(self) -> str:
        return (
            f"ReferenceLinkingResult(doc_id={self.doc_id!r}, "
            f"refs_found={self.references_found}, "
            f"links={self.internal_links_created + self.external_links_created})"
        )


class LegalReferenceLinker(Step):
    """
    Pipeline step that extracts legal references from article text 
    and creates REFERS_TO relationships in the graph.
    
    OPTIMIZED for batch operations:
    - Pre-fetches internal article map (80% of references are internal)
    - Caches external normativa lookups with @lru_cache
    - Batches all relationship writes into single database call
    """
    
    # Relationship types based on reference context
    REL_REFERS_TO = "REFERS_TO"
    REL_CITES = "CITES"           # For judicial decisions
    REL_DEROGATES = "DEROGATES"   # When "DEROGA" is in context
    REL_MODIFIES = "MODIFIES"     # When "MODIFICA" is in context
    
    def __init__(
        self, 
        name: str, 
        adapter: Neo4jAdapter,
        unresolved_log_path: Optional[str] = None
    ):
        super().__init__(name)
        self.adapter = adapter
        self.extractor = ReferenceExtractor(unresolved_log_path=unresolved_log_path)
        # Clear cache between documents
        self._find_normativa_cached.cache_clear()
        
    def process(self, data: GraphConstructionResult) -> ReferenceLinkingResult:
        """
        Process the graph construction result and create reference links.
        
        OPTIMIZED: Collects all relationships, then batch inserts.
        """
        if data is None:
            logger.warning("LegalReferenceLinker received None input")
            return ReferenceLinkingResult(doc_id="unknown")
        
        result = ReferenceLinkingResult(doc_id=data.doc_id)
        
        try:
            # 1. Fetch all articles for this normativa
            articles = self._fetch_articles(data.doc_id)
            result.articles_processed = len(articles)
            logger.info(f"Processing {len(articles)} articles for {data.doc_id}")
            
            # 2. Pre-build internal article lookup map (OPTIMIZATION)
            # This avoids database queries for 80% of references
            internal_article_map = self._build_internal_article_map(articles)
            
            # 3. Collect all relationships to batch insert
            relationships_to_create: List[Dict[str, Any]] = []
            
            for article in articles:
                article_id = article["id"]
                article_text = article.get("full_text") or article.get("text", "")
                article_name = article.get("name", "")
                
                if not article_text:
                    continue
                
                # Extract current article number
                current_art_match = re.search(r'\d+', article_name or '')
                current_article_num = current_art_match.group(0) if current_art_match else None
                
                # Extract references
                extraction = self.extractor.extract(
                    text=article_text,
                    source_document_id=article_id,
                    current_normativa_id=data.doc_id,
                    current_article_number=current_article_num
                )
                
                result.references_found += len(extraction.references)
                result.unresolved_references += len(extraction.unresolved_references)
                
                # Build relationships (but don't insert yet)
                referencer_fecha = article.get("fecha_vigencia")
                for ref in extraction.references:
                    rel_data = self._build_reference_link(
                        article_id, ref, data.doc_id, 
                        referencer_fecha, internal_article_map
                    )
                    if rel_data:
                        relationships_to_create.append(rel_data)
                        if ref.is_external:
                            result.external_links_created += 1
                        else:
                            result.internal_links_created += 1
            
            # 4. Batch insert all relationships (SINGLE DATABASE CALL)
            if relationships_to_create:
                self._batch_create_relationships(relationships_to_create)
                logger.info(f"Batch created {len(relationships_to_create)} reference links")
            
            # Log result
            logger.info(
                f"LegalReferenceLinker complete: {result.references_found} refs found, "
                f"{result.internal_links_created} internal + {result.external_links_created} external links"
            )
            
            self._add_tracing_attributes(result)
            
        except Exception as e:
            logger.error(f"Error in LegalReferenceLinker: {e}", exc_info=True)
            result.errors.append(str(e))
            raise
        
        return result
    
    def _fetch_articles(self, normativa_id: str) -> List[Dict[str, Any]]: #this supposes that articles are directly linked to the normativa
        """Fetch all articles belonging to a normativa."""
        query = """
        MATCH (a:articulo)-[:PART_OF]->(n:Normativa {id: $normativa_id}) 
        RETURN a.id as id, a.full_text as full_text, a.text as text, 
               a.name as name, a.fecha_vigencia as fecha_vigencia
        """
        return self.adapter.run_query(query, {"normativa_id": normativa_id})
    
    def _build_internal_article_map(self, articles: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Build a map of article_number -> article_id for fast internal lookups.
        
        This eliminates database queries for internal references (80% of all refs).
        """
        article_map = {}
        for article in articles:
            name = article.get("name", "")
            article_id = article.get("id")
            if name and article_id:
                # Extract number from "Artículo 14" -> "14"
                match = re.search(r'(\d+)', name)
                if match:
                    article_map[match.group(1)] = article_id
        return article_map
    
    def _build_reference_link(
        self, 
        source_article_id: str, 
        ref: ExtractedReference,
        current_normativa_id: str,
        referencer_fecha: Optional[str],
        internal_article_map: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """
        Build relationship data dict (but don't insert yet).
        Returns None if reference can't be resolved.
        """
        if ref.reference_type == ReferenceType.JUDICIAL:
            return None
        
        target_id = None
        target_label = None
        
        # Internal reference - use cached map (NO DATABASE QUERY!)
        if not ref.is_external:
            if ref.article_number and ref.article_number not in ("anterior", "siguiente", "precedente"):
                clean_num = ref.article_number.strip().rstrip('º\u00aa')
                target_id = internal_article_map.get(clean_num)
                target_label = "articulo"
        
        # External reference
        elif ref.resolved_boe_id:
            if ref.article_number:
                # External article lookup (still needs DB)
                target_id = self._find_article_in_normativa(
                    ref.resolved_boe_id, ref.article_number, referencer_fecha
                )
                target_label = "articulo"
            
            if not target_id:
                # Fall back to normativa (CACHED!)
                target_id = self._find_normativa_cached(ref.resolved_boe_id)
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
    
    @lru_cache(maxsize=1000)
    def _find_normativa_cached(self, normativa_id: str) -> Optional[str]:
        """Check if a Normativa exists (CACHED)."""
        query = """
        MATCH (n:Normativa {id: $normativa_id})
        RETURN n.id as id
        LIMIT 1
        """
        result = self.adapter.run_query_single(query, {"normativa_id": normativa_id})
        return result["id"] if result else None
    
    def _find_article_in_normativa(
        self, 
        normativa_id: str, 
        article_number: str,
        referencer_fecha: Optional[str] = None
    ) -> Optional[str]:
        """Find an article by clean_number within a normativa (O(1) exact lookup)."""
        # Normalize the article number to match clean_number format
        clean_num = self._normalize_article_number(article_number)
        
        # O(1) exact match on clean_number (uses index!)
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
    
    def _normalize_article_number(self, article_number: str) -> str:
        """Normalize article number to match clean_number format."""
        import re
        num = article_number.strip().rstrip('º\u00aa')
        # Extract number + suffix
        match = re.search(r'(\d+)(?:\s*(bis|ter|quater|quinquies|sexies|septies|octies|novies|[a-z]))?', num, re.IGNORECASE)
        if match:
            base = match.group(1)
            suffix = match.group(2)
            if suffix:
                return f"{base} {suffix.lower()}"
            return base
        return num
    
    def _determine_relationship_type(self, ref: ExtractedReference) -> str:
        """Determine the relationship type based on reference context."""
        raw_lower = ref.raw_text.lower()
        
        if "deroga" in raw_lower:
            return self.REL_DEROGATES
        elif "modifica" in raw_lower:
            return self.REL_MODIFIES
        else:
            return self.REL_REFERS_TO
    
    def _batch_create_relationships(self, relationships: List[Dict[str, Any]]) -> None:
        """Batch insert all relationships using the optimized adapter method."""
        # Add created_at timestamp to all
        for rel in relationships:
            if "props" not in rel:
                rel["props"] = {}
        
        self.adapter.batch_merge_relationships(relationships)
    
    def _add_tracing_attributes(self, result: ReferenceLinkingResult):
        """Add OpenTelemetry attributes if tracing is available."""
        if _tracer:
            current_span = trace.get_current_span()
            if current_span and current_span.is_recording():
                current_span.set_attribute("linker.doc_id", result.doc_id)
                current_span.set_attribute("linker.articles_processed", result.articles_processed)
                current_span.set_attribute("linker.references_found", result.references_found)
                current_span.set_attribute("linker.internal_links", result.internal_links_created)
                current_span.set_attribute("linker.external_links", result.external_links_created)
                current_span.set_attribute("linker.unresolved", result.unresolved_references)
