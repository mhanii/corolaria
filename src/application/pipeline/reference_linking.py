"""
Legal Reference Linker Pipeline Step.

Extracts legal references from article text and creates REFERS_TO relationships
in the graph between articles and referenced laws/articles.
"""
import logging
from typing import Optional, List, Dict, Any
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
    
    Prioritizes article-level links when possible:
    - "art. 14 de la Ley 10/1995" -> Links to specific article if it exists
    - "Ley 10/1995" (alone) -> Links to the Normativa node
    
    Creates relationships:
    - (:articulo)-[:REFERS_TO]->(:articulo)  # Article to article
    - (:articulo)-[:REFERS_TO]->(:Normativa) # Article to law (when no specific article)
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
        
    def process(self, data: GraphConstructionResult) -> ReferenceLinkingResult:
        """
        Process the graph construction result and create reference links.
        
        Args:
            data: GraphConstructionResult from previous step
            
        Returns:
            ReferenceLinkingResult with statistics
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
            
            # 2. Extract references from each article
            for article in articles:
                article_id = article["id"]
                article_text = article.get("full_text") or article.get("text", "")
                article_name = article.get("name", "")  # e.g., "Artículo 154"
                
                if not article_text:
                    continue
                
                # Extract current article number from name for resolving "anterior"
                import re
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
                
                # 3. Create relationships for resolved references
                for ref in extraction.references:
                    link_created = self._create_reference_link(article_id, ref, data.doc_id)
                    if link_created:
                        if ref.is_external:
                            result.external_links_created += 1
                        else:
                            result.internal_links_created += 1
            
            # Log result
            logger.info(
                f"LegalReferenceLinker complete: {result.references_found} refs found, "
                f"{result.internal_links_created} internal + {result.external_links_created} external links created"
            )
            
            # Add tracing attributes
            self._add_tracing_attributes(result)
            
        except Exception as e:
            logger.error(f"Error in LegalReferenceLinker: {e}", exc_info=True)
            result.errors.append(str(e))
            raise
        
        return result
    
    def _fetch_articles(self, normativa_id: str) -> List[Dict[str, Any]]:
        """Fetch all articles belonging to a normativa."""
        query = """
        MATCH (a:articulo)-[:PART_OF*1..10]->(n:Normativa {id: $normativa_id})
        RETURN a.id as id, a.full_text as full_text, a.text as text, a.name as name
        """
        return self.adapter.run_query(query, {"normativa_id": normativa_id})
    
    def _create_reference_link(
        self, 
        source_article_id: str, 
        ref: ExtractedReference,
        current_normativa_id: str
    ) -> bool:
        """
        Create a REFERS_TO relationship based on the extracted reference.
        
        Returns True if link was created, False otherwise.
        """
        # Skip judicial references (different relationship type, future work)
        if ref.reference_type == ReferenceType.JUDICIAL:
            return False
        
        target_id = None
        target_label = None
        
        # Internal reference - link to article within same normativa
        if not ref.is_external:
            if ref.article_number and ref.article_number not in ("anterior", "siguiente", "precedente"):
                # Try to find the specific article
                target_id = self._find_article_in_normativa(
                    current_normativa_id, 
                    ref.article_number
                )
                target_label = "articulo"
        
        # External reference with resolved BOE ID
        elif ref.resolved_boe_id:
            # If we have an article number, try to link to specific article
            if ref.article_number:
                target_id = self._find_article_in_normativa(
                    ref.resolved_boe_id,
                    ref.article_number
                )
                target_label = "articulo"
            
            # Fall back to linking to the Normativa itself
            if not target_id:
                target_id = self._find_normativa(ref.resolved_boe_id)
                target_label = "Normativa"
        
        # Create the relationship if we found a target
        if target_id:
            rel_type = self._determine_relationship_type(ref)
            return self._create_relationship(
                source_article_id, 
                target_id, 
                rel_type,
                target_label,
                ref.raw_text
            )
        
        return False
    
    def _find_article_in_normativa(self, normativa_id: str, article_number: str) -> Optional[str]:
        """Find an article by number within a normativa."""
        # Normalize article number for matching
        # "808" should NOT match "1808" - use word boundary regex
        clean_num = article_number.strip()
        
        # Remove ordinal markers for matching (269.4º -> 269.4)
        clean_num = clean_num.rstrip('ºª')
        
        # Build regex that matches article number with word boundaries
        # (?i) = case insensitive, \\b = word boundary
        # Matches: "Artículo 808", "Art. 808", "808 bis", etc.
        # Does NOT match: "1808" (because of word boundary before 808)
        query = """
        MATCH (a:articulo)-[:PART_OF*1..10]->(n:Normativa {id: $normativa_id})
        WHERE a.name =~ ('(?i).*\\\\b' + $article_num + '(\\\\b|º|ª|\\\\s+bis|\\\\s+ter|$).*')
        RETURN a.id as id
        LIMIT 1
        """
        result = self.adapter.run_query_single(query, {
            "normativa_id": normativa_id,
            "article_num": clean_num
        })
        return result["id"] if result else None
    
    def _find_normativa(self, normativa_id: str) -> Optional[str]:
        """Check if a Normativa exists and return its ID."""
        query = """
        MATCH (n:Normativa {id: $normativa_id})
        RETURN n.id as id
        LIMIT 1
        """
        result = self.adapter.run_query_single(query, {"normativa_id": normativa_id})
        return result["id"] if result else None
    
    def _determine_relationship_type(self, ref: ExtractedReference) -> str:
        """Determine the relationship type based on reference context."""
        # Check raw text for modification keywords
        raw_lower = ref.raw_text.lower()
        
        if "deroga" in raw_lower:
            return self.REL_DEROGATES
        elif "modifica" in raw_lower:
            return self.REL_MODIFIES
        else:
            return self.REL_REFERS_TO
    
    def _create_relationship(
        self, 
        source_id: str, 
        target_id: str, 
        rel_type: str,
        target_label: str,
        raw_text: str
    ) -> bool:
        """Create the actual relationship in the graph."""
        try:
            query = f"""
            MATCH (source:articulo {{id: $source_id}})
            MATCH (target:{target_label} {{id: $target_id}})
            MERGE (source)-[r:{rel_type}]->(target)
            SET r.raw_citation = $raw_text,
                r.created_at = datetime()
            RETURN type(r) as rel_type
            """
            result = self.adapter.run_write(query, {
                "source_id": source_id,
                "target_id": target_id,
                "raw_text": raw_text[:200]  # Truncate long citations
            })
            return result is not None
        except Exception as e:
            logger.warning(f"Failed to create relationship {source_id} -[{rel_type}]-> {target_id}: {e}")
            return False
    
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
