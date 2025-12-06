"""
Article API v1 endpoints.
RESTful endpoints for single article retrieval and version history.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status

from src.api.v1.schemas import (
    ArticleDetailResponse,
    ArticleVersionInfo,
    ArticleVersionsResponse,
    ErrorResponse
)
from src.api.v1.dependencies import get_neo4j_connection
from src.infrastructure.graphdb.connection import Neo4jConnection
from src.infrastructure.graphdb.adapter import Neo4jAdapter
from src.utils.logger import step_logger

# Create router for article endpoints
router = APIRouter()


def format_date(date_str: Optional[str]) -> Optional[str]:
    """
    Convert YYYYMMDD format to ISO format (YYYY-MM-DD).
    
    Args:
        date_str: Date in YYYYMMDD format (e.g., '19871123')
        
    Returns:
        ISO formatted date (e.g., '1987-11-23') or None
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


@router.get(
    "/article/{node_id}",
    response_model=ArticleDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Article by Node ID",
    description="Retrieve a single article by its node ID with full metadata",
    responses={
        200: {
            "description": "Article found",
            "model": ArticleDetailResponse
        },
        404: {
            "description": "Article not found",
            "model": ErrorResponse
        }
    }
)
async def get_article(
    node_id: int,
    connection: Neo4jConnection = Depends(get_neo4j_connection)
) -> ArticleDetailResponse:
    """
    Get a single article by node ID.
    
    Args:
        node_id: Unique node identifier for the article
        connection: Neo4j connection (injected)
    
    Returns:
        ArticleDetailResponse with full article metadata
    """
    step_logger.info(f"[ArticleAPI] Getting article: node_id={node_id}")
    
    adapter = Neo4jAdapter(connection)
    result = adapter.get_article_by_id(node_id)
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "ArticleNotFound",
                "message": f"Article with node_id '{node_id}' not found"
            }
        )
    
    return ArticleDetailResponse(
        node_id=str(result.get("node_id", "")),
        article_number=str(result.get("article_number", "")),
        article_text=result.get("article_text") or "",
        article_path=result.get("article_path") or "",
        normativa_title=str(result.get("normativa_title", "")),
        normativa_id=str(result.get("normativa_id", "")),
        fecha_publicacion=format_date(result.get("fecha_publicacion")),
        fecha_vigencia=format_date(result.get("fecha_vigencia")),
        fecha_caducidad=format_date(result.get("fecha_caducidad")),
        previous_version_id=str(result.get("previous_version_id")) if result.get("previous_version_id") else None,
        next_version_id=str(result.get("next_version_id")) if result.get("next_version_id") else None,
        context_path=result.get("context_path", [])
    )


@router.get(
    "/article/{node_id}/versions",
    response_model=ArticleVersionsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Article Versions",
    description="Retrieve all versions of an article (historical and current)",
    responses={
        200: {
            "description": "Versions found",
            "model": ArticleVersionsResponse
        },
        404: {
            "description": "Article not found",
            "model": ErrorResponse
        }
    }
)
async def get_article_versions(
    node_id: int,
    connection: Neo4jConnection = Depends(get_neo4j_connection)
) -> ArticleVersionsResponse:
    """
    Get all versions of an article.
    
    Args:
        node_id: Node ID of any version of the article
        connection: Neo4j connection (injected)
    
    Returns:
        ArticleVersionsResponse with all versions ordered chronologically
    """
    step_logger.info(f"[ArticleAPI] Getting versions for: node_id={node_id}")
    
    adapter = Neo4jAdapter(connection)
    versions = adapter.get_article_versions(node_id)
    
    if not versions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "ArticleNotFound",
                "message": f"Article with node_id '{node_id}' not found"
            }
        )
    
    # Determine which is the current version (no fecha_caducidad)
    version_infos = []
    for v in versions:
        is_current = v.get("validity_end") is None
        version_infos.append(ArticleVersionInfo(
            node_id=str(v.get("article_id", "")),
            article_number=str(v.get("article_number", "")),
            fecha_vigencia=format_date(v.get("validity_start")),
            fecha_caducidad=format_date(v.get("validity_end")),
            is_current_version=is_current,
            article_text=v.get("article_text") or ""
        ))
    
    # Get normativa info from first version
    normativa_title = versions[0].get("normativa_title", "") if versions else ""
    article_number = versions[0].get("article_number", "") if versions else ""
    
    return ArticleVersionsResponse(
        article_number=article_number,
        normativa_title=normativa_title,
        versions=version_infos,
        total_versions=len(version_infos)
    )
