"""
Citation Engine.
Maps RAG chunks to citations and extracts used citations from LLM responses.

Semantic Citation Format: [cite:cite_key]display_text[/cite]
Example: [cite:art_14_ce]Artículo 14[/cite]
"""
import re
import unicodedata
from typing import List, Dict, Any, Set, Tuple
from src.domain.models.citation import Citation
from src.utils.logger import step_logger


def _normalize_for_key(text: str) -> str:
    """
    Normalize text for use in citation keys.
    Removes accents, converts to lowercase, replaces spaces/special chars with underscores.
    """
    # Remove accents
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    # Lowercase and replace non-alphanumeric with underscore
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '_', text)
    text = text.strip('_')
    return text


def _generate_cite_key(article_number: str, normativa_title: str, article_id: str) -> str:
    """
    Generate a unique citation key from article metadata.
    
    Format: art_{normalized_article_number}_{normativa_abbrev}
    Falls back to article_id for uniqueness if needed.
    
    Examples:
        - "Artículo 14", "Constitución Española" -> "art_14_ce"
        - "Artículo 3.b", "Código Civil" -> "art_3b_cc"
    """
    # Extract article number (remove "Artículo " prefix if present)
    art_num = article_number.lower()
    art_num = re.sub(r'^art[íi]culo\s*', '', art_num)
    art_num = _normalize_for_key(art_num)
    
    # Create abbreviation from normativa title (first letters of main words)
    # Skip common words like "de", "la", "el", "del"
    stopwords = {'de', 'la', 'el', 'del', 'los', 'las', 'y', 'en', 'para'}
    words = normativa_title.lower().split()
    abbrev_parts = []
    for word in words:
        if word not in stopwords and word:
            # Take first letter, remove accents
            first = unicodedata.normalize('NFKD', word[0])
            first = ''.join(c for c in first if not unicodedata.combining(c))
            abbrev_parts.append(first)
    abbrev = ''.join(abbrev_parts[:4])  # Max 4 letters
    
    if not abbrev:
        abbrev = _normalize_for_key(normativa_title[:10])
    
    # Build key
    cite_key = f"art_{art_num}_{abbrev}" if art_num else f"ref_{abbrev}"
    
    # Add short hash from article_id for uniqueness
    if article_id:
        short_hash = article_id[-6:] if len(article_id) > 6 else article_id
        cite_key = f"{cite_key}_{short_hash}"
    
    return cite_key


class CitationEngine:
    """
    Engine for managing semantic citations in RAG-based chat responses.
    
    Citation Format: [cite:cite_key]display_text[/cite]
    
    Features:
    - Create citations from RAG retrieved chunks with unique cite_keys
    - Format context with semantic citation markers
    - Extract used citations and display_text from LLM response
    """
    
    # Regex pattern to match [cite:key]text[/cite]
    CITATION_PATTERN = re.compile(
        r'\[cite:([^\]]+)\](.+?)\[/cite\]',
        re.DOTALL
    )
    
    def __init__(self):
        """Initialize citation engine for semantic citations."""
        step_logger.info("[CitationEngine] Initialized with semantic citation format")
    
    def create_citations(self, chunks: List[Dict[str, Any]]) -> List[Citation]:
        """
        Create Citation objects from RAG retrieved chunks.
        
        Args:
            chunks: List of article result dicts from retrieval
            
        Returns:
            List of Citation objects with assigned cite_keys
        """
        citations = []
        seen_keys = set()  # Track used keys to ensure uniqueness
        
        for i, chunk in enumerate(chunks, start=1):
            article_id = str(chunk.get("article_id", ""))
            article_number = str(chunk.get("article_number", ""))
            normativa_title = str(chunk.get("normativa_title", ""))
            
            # Generate cite_key
            cite_key = _generate_cite_key(article_number, normativa_title, article_id)
            
            # Ensure uniqueness by appending counter if needed
            base_key = cite_key
            counter = 1
            while cite_key in seen_keys:
                cite_key = f"{base_key}_{counter}"
                counter += 1
            seen_keys.add(cite_key)
            
            # Get article path - prefer pre-computed, fall back to metadata
            article_path = chunk.get("article_path") or chunk.get("metadata", {}).get("context_path_text", "")
            
            citation = Citation(
                cite_key=cite_key,
                article_id=article_id,
                article_number=article_number,
                article_text=chunk.get("article_text", ""),
                normativa_title=normativa_title,
                article_path=article_path,
                display_text="",  # Will be filled when extracted from response
                score=float(chunk.get("score", 0.0)),
                metadata=chunk.get("metadata", {}),
                version_context=chunk.get("version_context", []),
                index=i  # Legacy field for compatibility
            )
            citations.append(citation)
        
        step_logger.info(f"[CitationEngine] Created {len(citations)} citations with cite_keys")
        
        return citations
    
    def format_context_with_citations(self, citations: List[Citation]) -> str:
        """
        Format citations into context string for LLM prompt.
        Shows the cite_key that the LLM should use to reference each source.
        
        Args:
            citations: List of Citation objects
            
        Returns:
            Formatted context string with cite_keys and version notes
        """
        if not citations:
            return ""
        
        context_parts = []
        
        for citation in citations:
            # Format: [Fuente: cite_key] Title - Path
            # Article text...
            header = f"[Fuente: {citation.cite_key}] {citation.normativa_title}"
            if citation.article_path:
                header += f" - {citation.article_path}"
            if citation.article_number:
                header += f" ({citation.article_number})"
            
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
    ) -> Tuple[str, List[Citation]]:
        """
        Extract used citations from response and populate display_text.
        
        Unlike the old system, we don't reindex - we just filter to used citations
        and capture the display text from each citation in the response.
        
        Args:
            response: LLM response text with [cite:key]text[/cite] format
            citations: All available citations
            
        Returns:
            Tuple of (response, used_citations_with_display_text)
            - response: Original response (unchanged)
            - used_citations: Citations that were referenced, with display_text populated
        """
        # Build a map of cite_key -> citation for quick lookup
        citation_map = {c.cite_key: c for c in citations}
        
        # Find all citation matches in response
        matches = self.CITATION_PATTERN.findall(response)
        
        # Track used citations and their display texts
        used_citations = []
        seen_keys = set()
        
        for cite_key, display_text in matches:
            cite_key = cite_key.strip()
            display_text = display_text.strip()
            
            if cite_key in citation_map and cite_key not in seen_keys:
                seen_keys.add(cite_key)
                # Create a copy with display_text populated
                original = citation_map[cite_key]
                used_citation = Citation(
                    cite_key=original.cite_key,
                    article_id=original.article_id,
                    article_number=original.article_number,
                    article_text=original.article_text,
                    normativa_title=original.normativa_title,
                    article_path=original.article_path,
                    display_text=display_text,
                    score=original.score,
                    metadata=original.metadata,
                    version_context=original.version_context,
                    index=len(used_citations) + 1  # Legacy sequential index
                )
                used_citations.append(used_citation)
            elif cite_key not in citation_map:
                step_logger.warning(f"[CitationEngine] Unknown cite_key in response: {cite_key}")
        
        step_logger.info(f"[CitationEngine] Extracted {len(used_citations)} citations from response")
        
        return response, used_citations
    
    def extract_citations_from_response(
        self, 
        response: str, 
        citations: List[Citation]
    ) -> List[Citation]:
        """
        Extract which citations were actually used in the LLM response.
        DEPRECATED: Use extract_and_reindex_citations instead.
        
        Args:
            response: LLM response text
            citations: All available citations
            
        Returns:
            List of citations that were referenced in the response
        """
        _, used_citations = self.extract_and_reindex_citations(response, citations)
        return used_citations
    
    def format_citation_marker(self, cite_key: str, display_text: str = "") -> str:
        """
        Format a single citation marker.
        
        Args:
            cite_key: Citation key
            display_text: Text to show in citation
            
        Returns:
            Formatted citation marker string
        """
        if not display_text:
            display_text = cite_key
        return f"[cite:{cite_key}]{display_text}[/cite]"

