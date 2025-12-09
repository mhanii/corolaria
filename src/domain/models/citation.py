"""
Citation data models.
Represents source citations for RAG-based responses.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List


@dataclass
class Citation:
    """
    Represents a citation to a source article.
    Used to track which RAG chunks are referenced in LLM responses.
    
    Semantic citation format: [cite:cite_key]display_text[/cite]
    Example: [cite:art_14_ce]Artículo 14[/cite]
    """
    cite_key: str  # Unique citation key like "art_14_ce" for [cite:key]
    article_id: str
    article_number: str
    article_text: str
    normativa_title: str
    article_path: str
    display_text: str = ""  # Text shown in citation (e.g., "Artículo 14.b")
    score: float = 0.0  # Retrieval similarity score
    metadata: Dict[str, Any] = field(default_factory=dict)
    version_context: List[Dict[str, Any]] = field(default_factory=list)  # Related versions
    # Legacy field for backward compatibility during transition
    index: int = 0  # Deprecated: use cite_key instead
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "cite_key": self.cite_key,
            "display_text": self.display_text,
            "article_id": self.article_id,
            "article_number": self.article_number,
            "article_text": self.article_text,
            "normativa_title": self.normativa_title,
            "article_path": self.article_path,
            "score": self.score,
            "metadata": self.metadata
        }
    
    def to_summary_dict(self) -> Dict[str, Any]:
        """Convert to summary dictionary (without full text)."""
        return {
            "cite_key": self.cite_key,
            "display_text": self.display_text,
            "article_id": self.article_id,
            "article_number": self.article_number,
            "normativa_title": self.normativa_title,
            "article_path": self.article_path,
            "score": self.score
        }

