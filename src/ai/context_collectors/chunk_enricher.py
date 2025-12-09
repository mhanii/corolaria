"""
Chunk Enricher Utility.

Post-processing for RAG chunks:
1. Validity checking - hop to latest version if outdated
2. Reference expansion - include REFERS_TO articles

This utility is shared by all context collectors (RAG, QRAG, etc.)
to ensure consistent behavior across retrieval strategies.
"""
from typing import List, Dict, Any, Set
from src.infrastructure.graphdb.adapter import Neo4jAdapter
from src.utils.logger import step_logger

# Import tracer for Phoenix observability
try:
    from opentelemetry import trace
    _tracer = trace.get_tracer("chunk_enricher")
except ImportError:
    _tracer = None


class ChunkEnricher:
    """
    Enriches RAG chunks with validity checking and reference expansion.
    
    Processing order:
    1. Check validity - if article has next_version_id, hop to latest version
    2. Expand references - add REFERS_TO articles (up to max_refs)
    
    Attributes:
        adapter: Neo4j adapter for graph queries
        max_refs: Maximum REFERS_TO articles to include per chunk
    """
    
    DEFAULT_MAX_REFS = 3
    
    def __init__(self, adapter: Neo4jAdapter, max_refs: int = DEFAULT_MAX_REFS):
        """
        Initialize the chunk enricher.
        
        Args:
            adapter: Neo4j adapter for database queries
            max_refs: Maximum REFERS_TO articles to include per original chunk
        """
        self._adapter = adapter
        self.max_refs = max_refs
        step_logger.info(f"[ChunkEnricher] Initialized with max_refs={max_refs}")
    
    def enrich_chunks(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enrich chunks with validity info and referenced articles.
        
        Order of operations:
        1. Check validity and hop to latest version if outdated
        2. Expand REFERS_TO relationships
        
        Args:
            chunks: Raw chunks from vector search
            
        Returns:
            Enriched chunks with referenced articles appended
        """
        if _tracer:
            with _tracer.start_as_current_span("ChunkEnricher.enrich_chunks") as span:
                span.set_attribute("input.chunks_count", len(chunks))
                span.set_attribute("config.max_refs", self.max_refs)
                
                result = self._do_enrich(chunks)
                
                span.set_attribute("output.chunks_count", len(result))
                span.set_attribute("output.hopped_versions", 
                    sum(1 for c in result if c.get("_outdated_version")))
                span.set_attribute("output.referred_articles",
                    sum(1 for c in result if c.get("_source") == "refers_to"))
                
                return result
        else:
            return self._do_enrich(chunks)
    
    def _do_enrich(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Internal enrichment logic with detailed tracing."""
        enriched: List[Dict[str, Any]] = []
        seen_ids: Set[str] = set()
        
        # Track detailed enrichment info for tracing
        enrichment_details: List[Dict[str, Any]] = []
        
        for chunk in chunks:
            article_id = chunk.get("article_id")
            article_number = chunk.get("article_number", "unknown")
            if not article_id:
                continue
            
            # Per-source tracking
            source_info: Dict[str, Any] = {
                "source_id": article_id,
                "source_article": article_number,
                "version_hopped": False,
                "hopped_to": None,
                "refers_to": []
            }
            
            # Step 1: Validity check and version hopping
            processed_chunk = self._check_validity_and_hop(chunk)
            current_id = processed_chunk.get("article_id")
            
            # Track version hop if it happened
            if current_id != article_id:
                source_info["version_hopped"] = True
                source_info["hopped_to"] = {
                    "id": current_id,
                    "article": processed_chunk.get("article_number", "unknown")
                }
                step_logger.info(
                    f"[ChunkEnricher] VERSION HOP: {article_number} ({article_id}) → "
                    f"{processed_chunk.get('article_number')} ({current_id})"
                )
            
            # Add the (possibly updated) chunk if not seen
            if current_id and current_id not in seen_ids:
                seen_ids.add(current_id)
                enriched.append(processed_chunk)
            
            # Step 2: Expand REFERS_TO relationships
            if current_id:
                referred = self._expand_references(current_id)
                refs_added = []
                for ref in referred:
                    ref_id = ref.get("article_id")
                    ref_article = ref.get("article_number", "unknown")
                    if ref_id and ref_id not in seen_ids:
                        seen_ids.add(ref_id)
                        # Mark as referenced and from where
                        ref["_source"] = "refers_to"
                        ref["_referred_from"] = current_id
                        ref["score"] = 0  # No similarity score for references
                        enriched.append(ref)
                        refs_added.append({"id": ref_id, "article": ref_article})
                
                if refs_added:
                    source_info["refers_to"] = refs_added
                    step_logger.info(
                        f"[ChunkEnricher] REFS EXPANDED: {article_number} ({article_id}) → "
                        f"{[r['article'] for r in refs_added]}"
                    )
            
            enrichment_details.append(source_info)
        
        # Log comprehensive summary
        step_logger.info(
            f"[ChunkEnricher] Enriched {len(chunks)} → {len(enriched)} chunks "
            f"(+{len(enriched) - len(chunks)} from references/hopping)"
        )
        
        # Add detailed tracing if available
        if _tracer:
            span = trace.get_current_span()
            if span and span.is_recording():
                # Structured enrichment summary
                for i, detail in enumerate(enrichment_details):
                    prefix = f"enrichment.source_{i}"
                    span.set_attribute(f"{prefix}.id", str(detail["source_id"]))
                    span.set_attribute(f"{prefix}.article", detail["source_article"])
                    span.set_attribute(f"{prefix}.version_hopped", detail["version_hopped"])
                    if detail["version_hopped"]:
                        span.set_attribute(f"{prefix}.hopped_to_id", str(detail["hopped_to"]["id"]))
                        span.set_attribute(f"{prefix}.hopped_to_article", detail["hopped_to"]["article"])
                    span.set_attribute(f"{prefix}.refers_to_count", len(detail["refers_to"]))
                    if detail["refers_to"]:
                        span.set_attribute(
                            f"{prefix}.refers_to_ids", 
                            str([r["id"] for r in detail["refers_to"]])
                        )
                        span.set_attribute(
                            f"{prefix}.refers_to_articles",
                            str([r["article"] for r in detail["refers_to"]])
                        )
        
        return enriched
    
    def _check_validity_and_hop(self, chunk: Dict[str, Any]) -> Dict[str, Any]:
        """
        If chunk has next_version_id, hop to latest version and annotate.
        
        Args:
            chunk: Original chunk data
            
        Returns:
            Either original chunk or latest version with outdated annotation
        """
        if chunk.get("next_version_id"):
            # This chunk references an outdated article version
            article_id = chunk.get("article_id")
            step_logger.info(
                f"[ChunkEnricher] Article {article_id} is outdated, hopping to latest version"
            )
            
            latest = self._adapter.get_latest_version(article_id)
            if latest and latest.get("article_id") != article_id:
                # Annotate with outdated version info
                latest["_outdated_version"] = {
                    "original_id": article_id,
                    "original_article_number": chunk.get("article_number"),
                    "message": "Este artículo ha sido modificado. Se muestra la versión vigente."
                }
                # Preserve original similarity score
                latest["score"] = chunk.get("score", 0)
                return latest
        
        return chunk
    
    def _expand_references(self, article_id: str) -> List[Dict[str, Any]]:
        """
        Get articles that this article refers to.
        
        Args:
            article_id: ID of the source article
            
        Returns:
            List of referenced article data
        """
        referred = self._adapter.get_referred_articles(article_id, self.max_refs)
        if referred:
            step_logger.debug(
                f"[ChunkEnricher] Article {article_id} has {len(referred)} references"
            )
        return referred
