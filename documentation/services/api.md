# API Service

## Overview

The **API Service** exposes the Coloraria functionality via a RESTful HTTP API built with **FastAPI**. It handles authentication, request validation, and routing to the underlying application services.

**Location**: `src/api/`

## Structure

*   `src/api/main.py`: Entry point. Configures middleware (CORS, trusted hosts), exception handlers, and mounts routers.
*   `src/api/v1/`: Version 1 endpoints.

## Endpoints

### Chat (`/api/v1/chat`)

*   `POST /api/v1/chat`: Standard chat endpoint.
    *   **Input**: JSON with `message`, `conversation_id`, `top_k`.
    *   **Output**: JSON with `response`, `conversation_id`, `citations`.
*   `POST /api/v1/chat/stream`: Streaming chat endpoint (SSE).
    *   **Output**: Server-Sent Events stream (`chunk`, `citations`, `done`).

### Articles (`/api/v1/article`)

*   `GET /api/v1/article/{node_id}`: Get full details of an article.
    *   **Returns**: Text, metadata, hierarchy path, versions links.
*   `GET /api/v1/article/{node_id}/versions`: Get all versions (history) of an article.

### Management

*   `DELETE /api/v1/chat/{conversation_id}`: Delete a conversation history.

## Error Handling

Standardized JSON error response:

```json
{
  "error": "ErrorType",
  "message": "Human readable message",
  "details": { ... }
}
```

## Authentication

Uses Bearer Token authentication (implied by `Authorization: Bearer <token>` in examples). Middleware parses and validates tokens for secure endpoints.
