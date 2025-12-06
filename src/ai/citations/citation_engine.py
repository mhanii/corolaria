"""
Citation Engine.
Maps RAG chunks to citations and extracts used citations from LLM responses.
"""
import re
from typing import List, Dict, Any, Set
from src.domain.models.citation import Citation
from src.utils.logger import step_logger


class CitationEngine:
    """
    Engine for managing citations in RAG-based chat responses.
    
    Features:
    - Create citations from RAG retrieved chunks
    - Format context with citation markers
    - Extract used citations from LLM response text
    """
    
    def __init__(self, citation_format: str = "[{index}]"):
        """
        Initialize citation engine.
        
        Args:
            citation_format: Format string for citations (must contain {index})
        """
        self.citation_format = citation_format
        # Build regex pattern to match citations like [1], [2], etc.
        # Escape the format string and replace {index} with capture group
        escaped = re.escape(citation_format)
        pattern = escaped.replace(r"\{index\}", r"(\d+)")
        self.citation_pattern = re.compile(pattern)
        
        step_logger.info(f"[CitationEngine] Initialized with format='{citation_format}'")
    
    def create_citations(self, chunks: List[Dict[str, Any]]) -> List[Citation]:
        """
        Create Citation objects from RAG retrieved chunks.
        
        Args:
            chunks: List of article result dicts from retrieval
            
        Returns:
            List of Citation objects with assigned indices
        """
        citations = []
        
        for i, chunk in enumerate(chunks, start=1):
            # Get article path - prefer pre-computed, fall back to metadata
            article_path = chunk.get("article_path") or chunk.get("metadata", {}).get("context_path_text", "")
            
            citation = Citation(
                index=i,
                article_id=str(chunk.get("article_id", "")),
                article_number=str(chunk.get("article_number", "")),
                article_text=chunk.get("article_text", ""),
                normativa_title=str(chunk.get("normativa_title", "")),
                article_path=article_path,
                score=float(chunk.get("score", 0.0)),
                metadata=chunk.get("metadata", {}),
                version_context=chunk.get("version_context", [])  # Include version context
            )
            citations.append(citation)
        
        step_logger.info(f"[CitationEngine] Created {len(citations)} citations")
        
        return citations
    
    def format_context_with_citations(self, citations: List[Citation]) -> str:
        """
        Format citations into context string for LLM prompt.
        Includes version context when available.
        
        Args:
            citations: List of Citation objects
            
        Returns:
            Formatted context string with source markers and version notes
        """
        if not citations:
            return ""
        
        context_parts = []
        
        for citation in citations:
            marker = self.citation_format.format(index=citation.index)
            
            # Format: [Source N] Title - Path
            # Article text...
            header = f"{marker} {citation.normativa_title}"
            if citation.article_path:
                header += f" - {citation.article_path}"
            
            entry = f"{header}\n{citation.article_text}"
            
            # Add version context if present
            if citation.version_context:
                version_notes = []
                
                # Process next versions (newer)
                next_versions = [v for v in citation.version_context if v.get("type") == "next"]
                if next_versions:
                    version_notes.append("\n---\nNota: Este artículo fue modificado posteriormente:")
                    for v in next_versions:
                        fecha = v.get("fecha_vigencia", "fecha desconocida")
                        version_notes.append(f"\nVersión vigente desde {fecha}:")
                        version_notes.append(v.get("text", ""))
                
                # Process previous versions (older)
                prev_versions = [v for v in citation.version_context if v.get("type") == "previous"]
                if prev_versions:
                    version_notes.append("\n---\nNota: Versión anterior de este artículo:")
                    for v in prev_versions:
                        fecha = v.get("fecha_vigencia", "fecha desconocida")
                        version_notes.append(f"\nVersión desde {fecha}:")
                        version_notes.append(v.get("text", ""))
                
                entry += "\n".join(version_notes)
            
            context_parts.append(entry)
        
        context = "\n\n".join(context_parts)
        
        step_logger.info(f"[CitationEngine] Formatted context ({len(context)} chars)")
        
        return context
    
    def extract_and_reindex_citations(
        self, 
        response: str, 
        citations: List[Citation]
    ) -> tuple[str, List[Citation]]:
        """
        Extract used citations, re-index them sequentially, and rewrite the response.
        
        Args:
            response: LLM response text
            citations: All available citations
            
        Returns:
            Tuple of (rewritten_response, reindexed_citations)
            - rewritten_response: Response with citations renumbered to [1], [2], etc.
            - reindexed_citations: Citations with new sequential indices
        """
        # Find all citation indices in response (preserve order of first appearance)
        matches = self.citation_pattern.findall(response)
        seen_indices: list[int] = []
        
        for match in matches:
            try:
                idx = int(match)
                if idx not in seen_indices:
                    seen_indices.append(idx)
            except ValueError:
                continue
        
        # Build old_index -> new_index mapping (1-based sequential)
        index_map: dict[int, int] = {}
        for new_idx, old_idx in enumerate(seen_indices, start=1):
            index_map[old_idx] = new_idx
        
        # Filter and re-index citations
        reindexed_citations = []
        for citation in citations:
            if citation.index in index_map:
                # Create a copy with the new index
                new_citation = Citation(
                    index=index_map[citation.index],
                    article_id=citation.article_id,
                    article_number=citation.article_number,
                    article_text=citation.article_text,
                    normativa_title=citation.normativa_title,
                    article_path=citation.article_path,
                    score=citation.score,
                    metadata=citation.metadata,
                    version_context=citation.version_context
                )
                reindexed_citations.append(new_citation)
        
        # Sort by new index
        reindexed_citations.sort(key=lambda c: c.index)
        
        # Rewrite response text: replace old indices with new ones
        rewritten_response = response
        for old_idx, new_idx in index_map.items():
            old_marker = self.citation_format.format(index=old_idx)
            new_marker = self.citation_format.format(index=new_idx)
            rewritten_response = rewritten_response.replace(old_marker, f"__CITE_{new_idx}__")
        
        # Second pass: replace placeholders with actual markers (to avoid conflicts)
        for new_idx in index_map.values():
            rewritten_response = rewritten_response.replace(
                f"__CITE_{new_idx}__", 
                self.citation_format.format(index=new_idx)
            )
        
        step_logger.info(f"[CitationEngine] Reindexed {len(reindexed_citations)} citations")
        
        return rewritten_response, reindexed_citations
    
    def extract_citations_from_response(
        self, 
        response: str, 
        citations: List[Citation]
    ) -> List[Citation]:
        """
        Extract which citations were actually used in the LLM response.
        DEPRECATED: Use extract_and_reindex_citations for sequential numbering.
        
        Args:
            response: LLM response text
            citations: All available citations
            
        Returns:
            List of citations that were referenced in the response
        """
        # Find all citation indices in response
        matches = self.citation_pattern.findall(response)
        used_indices: Set[int] = set()
        
        for match in matches:
            try:
                idx = int(match)
                used_indices.add(idx)
            except ValueError:
                continue
        
        # Filter to only used citations
        used_citations = [c for c in citations if c.index in used_indices]
        
        step_logger.info(f"[CitationEngine] Found {len(used_citations)} used citations in response")
        
        return used_citations
    
    def format_citation_marker(self, index: int) -> str:
        """
        Format a single citation marker.
        
        Args:
            index: Citation index
            
        Returns:
            Formatted citation marker string
        """
        return self.citation_format.format(index=index)
