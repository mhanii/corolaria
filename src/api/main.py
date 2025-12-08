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
from src.utils.logger import step_logger
from src.observability import setup_phoenix_tracing, shutdown_phoenix_tracing


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - setup and teardown."""
    # Startup
    step_logger.info("[API] Starting up Coloraria API...")
    setup_phoenix_tracing(project_name="coloraria-rag")
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
    
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "ValidationError",
            "message": "Invalid request parameters",
            "details": exc.errors()
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
            "article_versions": "/api/v1/article/{node_id}/versions"
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
