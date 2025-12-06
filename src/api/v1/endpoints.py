"""
API v1 endpoint handlers for semantic search.
"""
import time
from typing import List, Dict
from fastapi import APIRouter, Depends, HTTPException, status

from src.api.v1.schemas import (
    SemanticSearchRequest,
    SemanticSearchResponse,
    ArticleResult,
    ErrorResponse
)
from src.api.v1.dependencies import (
    get_neo4j_connection,
    get_embedding_provider
)
from src.infrastructure.graphdb.connection import Neo4jConnection
from src.infrastructure.graphdb.adapter import Neo4jAdapter
from src.domain.interfaces.embedding_provider import EmbeddingProvider
from src.utils.logger import step_logger

# Create router for v1 endpoints
router = APIRouter()


def format_context_path(context_path: List[Dict[str, str]]) -> str:
    """
    Format context path for Spanish-friendly, human-readable display.
    
    Converts: [{"type": "Título", "name": "I"}, {"type": "Capítulo", "name": "SEGUNDO"}]
    To: "Título I, Capítulo Segundo"
    
    Args:
        context_path: Raw context path from database (root to leaf)
    
    Returns:
        Formatted string with proper capitalization and order
    """
    if not context_path:
        return ""
    
    # Filter out ROOT and Content nodes
    filtered = [
        item for item in context_path 
        if item.get("type", "").upper() not in ("ROOT", "CONTENT")
    ]
    
    if not filtered:
        return ""
    
    # Reverse to get leaf-to-root order (more natural for Spanish)
    reversed_path = list(reversed(filtered))
    
    # Format each item with proper capitalization
    formatted_items = []
    for item in reversed_path:
        item_type = item.get("type", "").capitalize()
        item_name = item.get("name", "")
        
        # Convert ALL CAPS names to Title Case for readability
        if item_name.isupper() and len(item_name) > 1:
            item_name = item_name.title()
        
        formatted_items.append(f"{item_type} {item_name}")
    
    # Join with comma and space for Spanish readability
    return ", ".join(formatted_items)


def format_date(date_str: str) -> str:
    """
    Convert YYYYMMDD format to ISO format (YYYY-MM-DD).
    
    Args:
        date_str: Date in YYYYMMDD format (e.g., '19871123')
        
    Returns:
        ISO formatted date (e.g., '1987-11-23') or original string if invalid
    """
    if not date_str or len(date_str) != 8:
        return date_str
    
    try:
        year = date_str[:4]
        month = date_str[4:6]
        day = date_str[6:8]
        return f"{year}-{month}-{day}"
    except (ValueError, IndexError):
        return date_str



@router.post(
    "/search/semantic",
    response_model=SemanticSearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Semantic Search",
    description="Perform semantic search on legal articles using vector embeddings",
    responses={
        200: {
            "description": "Successful search with results",
            "model": SemanticSearchResponse
        },
        400: {
            "description": "Invalid request (e.g., empty query)",
            "model": ErrorResponse
        },
        500: {
            "description": "Internal server error (database or embedding failure)",
            "model": ErrorResponse
        }
    }
)
async def semantic_search(
    request: SemanticSearchRequest,
    connection: Neo4jConnection = Depends(get_neo4j_connection),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider)
) -> SemanticSearchResponse:
    """
    Perform semantic search on legal articles.
    
    This endpoint:
    1. Generates an embedding for the query using Gemini
    2. Searches the Neo4j vector index for similar articles
    3. Returns ranked results with context and metadata
    
    Args:
        request: Search request with query and parameters
        connection: Neo4j connection (injected)
        embedding_provider: Gemini embedding provider (injected)
    
    Returns:
        SemanticSearchResponse with matching articles
    
    Raises:
        HTTPException: If query is invalid or if processing fails
    """
    start_time = time.time()
    
    try:
        step_logger.info(f"[API] Semantic search request: query='{request.query}', top_k={request.top_k}")
        
        # Create adapter from connection
        adapter = Neo4jAdapter(connection)
        
        # Generate query embedding
        try:
            query_embedding = embedding_provider.get_embedding(request.query)
            step_logger.info(f"[API] Generated query embedding (dim={len(query_embedding)})")
        except Exception as e:
            step_logger.error(f"[API] Failed to generate embedding: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "EmbeddingGenerationError",
                    "message": "Failed to generate query embedding",
                    "details": {"exception": str(e)}
                }
            )
        
        # Perform vector search
        try:
            raw_results = adapter.vector_search(
                query_embedding=query_embedding,
                top_k=request.top_k,
                index_name=request.index_name
            )
            step_logger.info(f"[API] Vector search returned {len(raw_results)} results")
        except Exception as e:
            step_logger.error(f"[API] Vector search failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "DatabaseError",
                    "message": "Failed to search vector database",
                    "details": {"exception": str(e)}
                }
            )
        
        # Transform results to response schema
        article_results: List[ArticleResult] = []
        for result in raw_results:
            # article_id MUST be int from Neo4j - enforce strict typing
            article_id: int = result.get("article_id")
            if not isinstance(article_id, int):
                step_logger.error(f"[API] Type error: article_id must be int, got {type(article_id).__name__}: {article_id}")
                raise TypeError(f"article_id must be int, got {type(article_id).__name__}")
            
            # Article text is now pre-computed and stored as full_text in Neo4j
            # No additional query needed (eliminates N+1 problem)
            article_text = result.get("article_text") or ""
            
            # Article path is pre-computed during ingestion
            article_path = result.get("article_path") or ""
            
            # Format context path for human-readable Spanish display (fallback if path not set)
            raw_context_path = result.get("context_path", [])
            formatted_context = article_path or format_context_path(raw_context_path)
            
            # Create Pydantic model with type conversions for API layer
            article_results.append(ArticleResult(
                article_id=str(article_id),  # Convert int to str for API schema
                article_number=str(result.get("article_number", "")),
                article_text=article_text,
                article_path=article_path,
                score=float(result.get("score", 0.0)),
                normativa_title=str(result.get("normativa_title", "")),
                normativa_id=str(result.get("normativa_id", "")),
                # Date fields from Neo4j (formatted to ISO)
                fecha_publicacion=format_date(result.get("fecha_publicacion")) if result.get("fecha_publicacion") else None,
                fecha_vigencia=format_date(result.get("fecha_vigencia")) if result.get("fecha_vigencia") else None,
                fecha_caducidad=format_date(result.get("fecha_caducidad")) if result.get("fecha_caducidad") else None,
                # Version IDs (convert to str if present)
                previous_version_id=str(result.get("previous_version_id")) if result.get("previous_version_id") else None,
                next_version_id=str(result.get("next_version_id")) if result.get("next_version_id") else None,
                context_path=raw_context_path,  # Keep raw for compatibility
                metadata={
                    "has_embedding": result.get("embedding") is not None,
                    "query": request.query,
                    "context_path_text": formatted_context  # Human-readable Spanish version
                }
            ))
        
        # Calculate execution time
        execution_time_ms = (time.time() - start_time) * 1000
        step_logger.info(f"[API] Request completed in {execution_time_ms:.2f}ms")
        
        # Build and return response
        return SemanticSearchResponse(
            query=request.query,
            results=article_results,
            total_results=len(article_results),
            strategy_used="Vector Search",
            execution_time_ms=execution_time_ms
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Catch-all for unexpected errors
        step_logger.error(f"[API] Unexpected error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "InternalServerError",
                "message": "An unexpected error occurred",
                "details": {"exception": str(e)}
            }
        )
