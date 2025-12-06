"""
Pydantic schemas for API v1 request and response models.
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator


class SemanticSearchRequest(BaseModel):
    """Request schema for semantic search endpoint."""
    
    query: str = Field(
        ..., 
        min_length=1,
        description="The search query text",
        examples=["libertad de expresión", "derechos fundamentales"]
    )
    top_k: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Number of results to return (1-100)"
    )
    index_name: str = Field(
        default="article_embeddings",
        description="Vector index to use for search"
    )
    
    @field_validator('query')
    @classmethod
    def query_not_empty(cls, v: str) -> str:
        """Ensure query is not just whitespace."""
        if not v.strip():
            raise ValueError("Query cannot be empty or only whitespace")
        return v.strip()


class ArticleResult(BaseModel):
    """Schema for individual article result."""
    
    article_id: str = Field(..., description="Unique node identifier for the article")
    article_number: str = Field(..., description="Article number (e.g., 'Artículo 14')")
    article_text: str = Field(..., description="Full text content of the article")
    article_path: str = Field(
        default="",
        description="Human-readable hierarchy path (e.g., 'Título I, Capítulo II')"
    )
    score: float = Field(..., description="Similarity score (higher is better)")
    normativa_title: str = Field(..., description="Title of the regulation containing this article")
    normativa_id: str = Field(..., description="Unique identifier for the regulation")
    
    # Date fields
    fecha_publicacion: Optional[str] = Field(
        default=None,
        description="Publication date (ISO format or YYYYMMDD)"
    )
    fecha_vigencia: Optional[str] = Field(
        default=None,
        description="Validity start date (ISO format or YYYYMMDD)"
    )
    fecha_caducidad: Optional[str] = Field(
        default=None,
        description="Expiration date if superseded (ISO format or YYYYMMDD)"
    )
    
    # Version links (node IDs for API retrieval)
    previous_version_id: Optional[str] = Field(
        default=None,
        description="Node ID of the previous (older) version, if any"
    )
    next_version_id: Optional[str] = Field(
        default=None,
        description="Node ID of the next (newer) version, if any"
    )
    
    context_path: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Hierarchical context (e.g., Book > Title > Chapter)"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata about the result"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "article_id": "123",
                "article_number": "Artículo 14",
                "article_text": "Los españoles son iguales ante la ley...",
                "article_path": "Título I, Capítulo Segundo",
                "score": 0.89,
                "normativa_title": "Constitución Española de 1978",
                "normativa_id": "const_1978",
                "fecha_publicacion": "19781229",
                "fecha_vigencia": "19781229",
                "fecha_caducidad": None,
                "previous_version_id": None,
                "next_version_id": "456",
                "context_path": [
                    {"type": "Título", "name": "I"},
                    {"type": "Capítulo", "name": "Segundo"}
                ],
                "metadata": {
                    "has_embedding": True,
                    "query": "igualdad ante la ley"
                }
            }
        }


class SemanticSearchResponse(BaseModel):
    """Response schema for semantic search endpoint."""
    
    query: str = Field(..., description="The original query")
    results: List[ArticleResult] = Field(..., description="List of matching articles")
    total_results: int = Field(..., description="Total number of results returned")
    strategy_used: str = Field(default="Vector Search", description="Search strategy used")
    execution_time_ms: float = Field(..., description="Query execution time in milliseconds")
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "libertad de expresión",
                "results": [],
                "total_results": 5,
                "strategy_used": "Vector Search",
                "execution_time_ms": 342.5
            }
        }


class ErrorResponse(BaseModel):
    """Error response schema."""
    
    error: str = Field(..., description="Error type or category")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional error details"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "error": "ValidationError",
                "message": "Query cannot be empty",
                "details": {
                    "field": "query",
                    "provided_value": ""
                }
            }
        }


# =====================================================================
# Article Retrieval Schemas
# =====================================================================

class ArticleDetailResponse(BaseModel):
    """Detailed response for single article retrieval by node ID."""
    
    node_id: str = Field(..., description="Unique node identifier")
    article_number: str = Field(..., description="Article number (e.g., 'Artículo 14')")
    article_text: str = Field(..., description="Full text content of the article")
    article_path: str = Field(default="", description="Human-readable hierarchy path")
    normativa_title: str = Field(..., description="Title of the regulation")
    normativa_id: str = Field(..., description="Unique identifier for the regulation")
    
    # Date fields
    fecha_publicacion: Optional[str] = Field(default=None, description="Publication date")
    fecha_vigencia: Optional[str] = Field(default=None, description="Validity start date")
    fecha_caducidad: Optional[str] = Field(default=None, description="Expiration date if superseded")
    
    # Version links
    previous_version_id: Optional[str] = Field(default=None, description="Node ID of previous version")
    next_version_id: Optional[str] = Field(default=None, description="Node ID of next version")
    
    context_path: List[Dict[str, str]] = Field(default_factory=list, description="Hierarchical context")
    
    class Config:
        json_schema_extra = {
            "example": {
                "node_id": "123",
                "article_number": "Artículo 14",
                "article_text": "Los españoles son iguales ante la ley...",
                "article_path": "Título I, Capítulo Segundo",
                "normativa_title": "Constitución Española de 1978",
                "normativa_id": "const_1978",
                "fecha_vigencia": "19781229",
                "previous_version_id": None,
                "next_version_id": None
            }
        }


class ArticleVersionInfo(BaseModel):
    """Information about a single article version."""
    
    node_id: str = Field(..., description="Unique node identifier for this version")
    article_number: str = Field(..., description="Article number")
    fecha_vigencia: Optional[str] = Field(default=None, description="Validity start date")
    fecha_caducidad: Optional[str] = Field(default=None, description="Expiration date")
    is_current_version: bool = Field(default=False, description="Whether this is the current/latest version")
    article_text: str = Field(..., description="Full text of this version")


class ArticleVersionsResponse(BaseModel):
    """Response containing all versions of an article."""
    
    article_number: str = Field(..., description="Article number (e.g., 'Artículo 14')")
    normativa_title: str = Field(..., description="Title of the regulation")
    versions: List[ArticleVersionInfo] = Field(default_factory=list, description="All versions ordered chronologically")
    total_versions: int = Field(..., description="Total number of versions")
    
    class Config:
        json_schema_extra = {
            "example": {
                "article_number": "Artículo 14",
                "normativa_title": "Constitución Española de 1978",
                "versions": [
                    {
                        "node_id": "123",
                        "article_number": "Artículo 14",
                        "fecha_vigencia": "19781229",
                        "fecha_caducidad": "19920828",
                        "is_current_version": False,
                        "article_text": "Versión original..."
                    },
                    {
                        "node_id": "456",
                        "article_number": "Artículo 14",
                        "fecha_vigencia": "19920828",
                        "fecha_caducidad": None,
                        "is_current_version": True,
                        "article_text": "Versión modificada..."
                    }
                ],
                "total_versions": 2
            }
        }
