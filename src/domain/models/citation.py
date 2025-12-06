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
    """
    index: int  # Citation number [1], [2], etc.
    article_id: str
    article_number: str
    article_text: str
    normativa_title: str
    article_path: str
    score: float = 0.0  # Retrieval similarity score
    metadata: Dict[str, Any] = field(default_factory=dict)
    version_context: List[Dict[str, Any]] = field(default_factory=list)  # Related versions
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "index": self.index,
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
            "index": self.index,
            "article_id": self.article_id,
            "article_number": self.article_number,
            "normativa_title": self.normativa_title,
            "article_path": self.article_path,
            "score": self.score
        }
