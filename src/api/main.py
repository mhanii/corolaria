"""
FastAPI main application for Coloraria API.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from src.api.v1 import endpoints as v1_endpoints
from src.api.v1 import chat_endpoints as v1_chat
from src.api.v1 import article_endpoints as v1_article
from src.api.v1 import auth_endpoints as v1_auth
from src.api.v1 import beta_endpoints as v1_beta
from src.api.v1 import analytics_endpoints as v1_analytics
from src.utils.logger import step_logger
from src.observability import setup_phoenix_tracing, shutdown_phoenix_tracing


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - setup and teardown."""
    # Startup
    step_logger.info("[API] Starting up Coloraria API...")
    
    # 1. Initialize Phoenix tracing
    setup_phoenix_tracing(project_name="coloraria-rag")
    
    # 2. Initialize MariaDB connection
    try:
        from src.infrastructure.database import get_database_connection
        db = get_database_connection()
        step_logger.info("[API] ✓ MariaDB connection initialized")
    except Exception as e:
        step_logger.error(f"[API] ✗ MariaDB connection failed: {e}")
    
    # 3. Initialize Neo4j connection
    try:
        import os
        from src.infrastructure.graphdb.connection import Neo4jConnection
        neo4j_conn = Neo4jConnection(
            uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            user=os.getenv("NEO4J_USER", "neo4j"),
            password=os.getenv("NEO4J_PASSWORD", "password")
        )
        # Test connection
        neo4j_conn.verify_connectivity()
        step_logger.info("[API] ✓ Neo4j connection initialized")
    except Exception as e:
        step_logger.error(f"[API] ✗ Neo4j connection failed: {e}")
    
    # 4. Initialize LLM provider (uses singleton from dependencies)
    try:
        from src.api.v1.dependencies import get_llm_provider
        llm = get_llm_provider()  # Initializes and caches the singleton
        step_logger.info("[API] ✓ LLM provider initialized")
    except Exception as e:
        step_logger.error(f"[API] ✗ LLM provider failed: {e}")
    
    yield
    
    # Shutdown
    step_logger.info("[API] Shutting down Coloraria API...")
    shutdown_phoenix_tracing()


# Create FastAPI application
app = FastAPI(
    title="Coloraria API",
    description="Legal article semantic search, retrieval, and AI chat API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors."""
    step_logger.warning(f"[API] Validation error: {exc.errors()}")
    
    # Convert errors to JSON-serializable format (handle bytes in input)
    def make_serializable(obj):
        if isinstance(obj, bytes):
            return obj.decode('utf-8', errors='replace')
        elif isinstance(obj, dict):
            return {k: make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [make_serializable(item) for item in obj]
        return obj
    
    errors = make_serializable(exc.errors())
    
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "ValidationError",
            "message": "Invalid request parameters",
            "details": errors
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    step_logger.error(f"[API] Unhandled exception: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "InternalServerError",
            "message": "An unexpected error occurred",
            "details": {"exception": str(exc)}
        }
    )


# Health check endpoint
@app.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Health Check",
    description="Check if the API is running",
    tags=["Health"]
)
async def health_check():
    """
    Health check endpoint.
    
    Returns:
        Simple status message
    """
    return {
        "status": "healthy",
        "service": "Coloraria API",
        "version": "1.0.0"
    }


# Include v1 router (semantic search)
app.include_router(
    v1_endpoints.router,
    prefix="/api/v1",
    tags=["Search v1"]
)

# Include v1 chat router
app.include_router(
    v1_chat.router,
    prefix="/api/v1",
    tags=["Chat v1"]
)

# Include v1 article router
app.include_router(
    v1_article.router,
    prefix="/api/v1",
    tags=["Article v1"]
)

# Include v1 auth router
app.include_router(
    v1_auth.router,
    prefix="/api/v1",
    tags=["Authentication"]
)

# Include v1 beta testing router
app.include_router(
    v1_beta.router,
    prefix="/api/v1",
    tags=["Beta Testing"]
)

# Include v1 analytics router
app.include_router(
    v1_analytics.router,
    prefix="/api/v1",
    tags=["Analytics"]
)


# Root endpoint
@app.get(
    "/",
    summary="API Root",
    description="Get API information and available endpoints",
    tags=["Info"]
)
async def root():
    """
    Root endpoint with API information.
    
    Returns:
        API metadata and links
    """
    return {
        "name": "Coloraria API",
        "version": "1.0.0",
        "description": "Legal article semantic search, retrieval, and AI chat API",
        "documentation": "/docs",
        "endpoints": {
            "health": "/health",
            "login": "/api/v1/auth/login",
            "me": "/api/v1/auth/me",
            "semantic_search": "/api/v1/search/semantic",
            "chat": "/api/v1/chat",
            "conversations": "/api/v1/conversations",
            "chat_history": "/api/v1/chat/{conversation_id}",
            "article": "/api/v1/article/{node_id}",
            "article_versions": "/api/v1/article/{node_id}/versions",
            "beta_status": "/api/v1/beta/status",
            "beta_feedback": "/api/v1/beta/feedback",
            "beta_survey": "/api/v1/beta/survey",
            "analytics_summary": "/api/v1/analytics/summary",
            "analytics_daily": "/api/v1/analytics/daily",
            "analytics_events": "/api/v1/analytics/events"
        }
    }


if __name__ == "__main__":
    import uvicorn
    
    step_logger.info("Starting Coloraria API server...")
    
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
