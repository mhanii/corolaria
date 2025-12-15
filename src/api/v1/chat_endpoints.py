"""
Chat API v1 endpoints.
RESTful endpoints for AI chatbot with RAG-based citations.
Protected by JWT authentication with token-based rate limiting.
"""
import json
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from src.api.v1.chat_schemas import (
    ChatRequest,
    ChatResponse,
    CitationResponse,
    ConversationResponse,
    ConversationMessageResponse,
    DeleteResponse,
    CollectorType
)
from src.api.v1.auth import get_current_user_from_token, TokenPayload
from src.infrastructure.database import get_database_connection
from src.infrastructure.database.repository_factory import (
    get_user_repository as get_user_repo,
    get_conversation_repository as get_conv_repo
)
from src.api.v1.dependencies import (
    get_chat_service_with_user,
    get_chat_service_with_collector,
    get_neo4j_connection
)
from src.infrastructure.graphdb.connection import Neo4jConnection
from src.utils.logger import step_logger

# Create router for chat endpoints
router = APIRouter()


def get_repositories():
    """Get database repositories using abstraction layer."""
    connection = get_database_connection()
    return {
        "user": get_user_repo(connection),
        "conversation": get_conv_repo(connection)
    }


# ============ Conversation List Endpoint ============

class ConversationListItem:
    """Schema for conversation list item."""
    pass


from pydantic import BaseModel, Field


class ConversationSummary(BaseModel):
    """Summary of a conversation for listing."""
    id: str = Field(..., description="Conversation ID")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")
    message_count: int = Field(..., description="Number of messages")
    preview: str = Field(default=None, description="Preview of first message")


class ConversationListResponse(BaseModel):
    """Response for conversation list."""
    conversations: List[ConversationSummary] = Field(..., description="List of conversations")
    total: int = Field(..., description="Total number of conversations")


@router.get(
    "/conversations",
    response_model=ConversationListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Conversations",
    description="Get all conversations for the authenticated user",
    responses={
        200: {
            "description": "List of conversations",
            "model": ConversationListResponse
        },
        401: {
            "description": "Not authenticated"
        }
    }
)
async def list_conversations(
    token: TokenPayload = Depends(get_current_user_from_token)
) -> ConversationListResponse:
    """
    List all conversations for the current user.
    
    Args:
        token: JWT token payload (injected)
        
    Returns:
        List of conversation summaries
    """
    step_logger.info(f"[ChatAPI] Listing conversations for user: {token.username}")
    
    repos = get_repositories()
    conversations = repos["conversation"].list_conversations(token.user_id)
    
    return ConversationListResponse(
        conversations=[
            ConversationSummary(
                id=c["id"],
                created_at=c["created_at"],
                updated_at=c["updated_at"],
                message_count=c["message_count"],
                preview=c["preview"]
            )
            for c in conversations
        ],
        total=len(conversations)
    )


# ============ Chat Endpoint ============

@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Send Chat Message",
    description="Send a message to the AI chatbot and receive a response with source citations",
    responses={
        200: {
            "description": "Successful response with citations",
            "model": ChatResponse
        },
        400: {
            "description": "Invalid request (e.g., empty message)"
        },
        401: {
            "description": "Not authenticated"
        },
        402: {
            "description": "Insufficient tokens"
        },
        500: {
            "description": "Internal server error (LLM or retrieval failure)"
        }
    }
)
async def chat(
    request: ChatRequest,
    token: TokenPayload = Depends(get_current_user_from_token),
    connection: Neo4jConnection = Depends(get_neo4j_connection)
) -> ChatResponse:
    """
    Process a chat message and return AI response with citations.
    
    This endpoint:
    1. Verifies user has available tokens
    2. Retrieves relevant legal articles using semantic search
    3. Generates response using LLM with context
    4. Returns response with inline citations [1], [2], etc.
    5. Deducts token from user's balance
    
    Args:
        request: Chat request with message and optional conversation_id
        token: JWT token payload (injected)
        connection: Neo4j connection (injected)
    
    Returns:
        ChatResponse with AI response and source citations
    """
    step_logger.info(f"[ChatAPI] Received chat request from {token.username}: '{request.message[:50]}...'")
    
    repos = get_repositories()
    
    # Check token balance
    balance = repos["user"].get_token_balance(token.user_id)
    if balance <= 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "InsufficientTokens",
                "message": "You have no remaining API tokens. Complete a survey to refill.",
                "requires_refill": True,
                "survey_endpoint": "/api/v1/beta/survey"
            }
        )
    
    # Verify conversation ownership if continuing existing conversation
    if request.conversation_id:
        owner = repos["conversation"].get_conversation_user_id(request.conversation_id)
        if owner and owner != token.user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "ConversationNotFound",
                    "message": f"Conversation '{request.conversation_id}' not found"
                }
            )
    
    # Determine collector type
    # For new conversations: use request.collector_type and store it
    # For existing conversations: retrieve from metadata
    collector_type = "rag"  # default
    
    if request.conversation_id:
        # Existing conversation - retrieve collector_type from metadata
        metadata = repos["conversation"].get_metadata(request.conversation_id)
        stored_collector_type = metadata.get("collector_type")
        if stored_collector_type:
            collector_type = stored_collector_type
            step_logger.info(f"[ChatAPI] Using stored collector type: {collector_type}")
    elif request.collector_type:
        # New conversation with collector_type specified
        collector_type = request.collector_type.value
        step_logger.info(f"[ChatAPI] Using collector type: {collector_type}")
    
    # Create chat service with appropriate collector
    chat_service = get_chat_service_with_collector(connection, collector_type)
    
    try:
        result = await chat_service.achat(
            query=request.message,
            conversation_id=request.conversation_id,
            top_k=request.top_k,
            user_id=token.user_id
        )
        
        # For new conversations, store the collector_type in metadata
        if not request.conversation_id and request.collector_type:
            repos["conversation"].update_metadata(
                result.conversation_id, 
                {"collector_type": collector_type}
            )
        
        # Consume token
        repos["user"].consume_tokens(token.user_id, 1)
        
        # Convert citations to response format
        citation_responses = [
            CitationResponse(
                cite_key=c.cite_key,
                display_text=c.display_text,
                article_id=c.article_id,
                article_number=c.article_number,
                normativa_title=c.normativa_title,
                article_path=c.article_path,
                score=c.score
            )
            for c in result.citations
        ]
        
        step_logger.info(f"[ChatAPI] Response generated: {len(citation_responses)} citations")
        
        # Extract config_matrix from metadata if available
        config_matrix = result.metadata.get("config_matrix") if result.metadata else None
        
        return ChatResponse(
            response=result.response,
            conversation_id=result.conversation_id,
            citations=citation_responses,
            execution_time_ms=result.execution_time_ms,
            config_matrix=config_matrix
        )
        
    except Exception as e:
        step_logger.error(f"[ChatAPI] Chat error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "ChatProcessingError",
                "message": "Failed to process chat message",
                "details": {"exception": str(e)}
            }
        )


# ============ Streaming Chat Endpoint ============

@router.post(
    "/chat/stream",
    status_code=status.HTTP_200_OK,
    summary="Send Chat Message (Streaming)",
    description="Send a message and receive a streaming response via Server-Sent Events (SSE)",
    responses={
        200: {
            "description": "SSE stream with chunk, citations, and done events",
            "content": {
                "text/event-stream": {
                    "example": 'data: {"type": "chunk", "content": "El artículo"}\n\ndata: {"type": "done", "conversation_id": "abc123"}\n\n'
                }
            }
        },
        400: {"description": "Invalid request"},
        401: {"description": "Not authenticated"},
        402: {"description": "Insufficient tokens"}
    }
)
async def chat_stream(
    request: ChatRequest,
    token: TokenPayload = Depends(get_current_user_from_token),
    connection: Neo4jConnection = Depends(get_neo4j_connection)
) -> StreamingResponse:
    """
    Stream a chat response using Server-Sent Events (SSE).
    
    This endpoint streams the AI response in real-time as it's generated.
    The response is a series of SSE events:
    
    - `{"type": "chunk", "content": "..."}` - Partial response text
    - `{"type": "citations", "citations": [...]}` - Citation data (after response complete)
    - `{"type": "done", "conversation_id": "...", "execution_time_ms": ...}` - Completion marker
    - `{"type": "error", "message": "..."}` - Error if something fails
    
    Args:
        request: Chat request with message and optional conversation_id
        token: JWT token payload (injected)
        connection: Neo4j connection (injected)
    
    Returns:
        StreamingResponse with SSE events
    """
    step_logger.info(f"[ChatAPI] Received streaming chat request from {token.username}: '{request.message[:50]}...'")
    
    repos = get_repositories()
    
    # Check token balance
    balance = repos["user"].get_token_balance(token.user_id)
    if balance <= 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "InsufficientTokens",
                "message": "You have no remaining API tokens. Please contact an administrator."
            }
        )
    
    # Verify conversation ownership if continuing existing conversation
    if request.conversation_id:
        owner = repos["conversation"].get_conversation_user_id(request.conversation_id)
        if owner and owner != token.user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "ConversationNotFound",
                    "message": f"Conversation '{request.conversation_id}' not found"
                }
            )
    
    # Determine collector type
    collector_type = "rag"
    
    if request.conversation_id:
        metadata = repos["conversation"].get_metadata(request.conversation_id)
        stored_collector_type = metadata.get("collector_type")
        if stored_collector_type:
            collector_type = stored_collector_type
    elif request.collector_type:
        collector_type = request.collector_type.value
    
    # Create chat service with appropriate collector
    chat_service = get_chat_service_with_collector(connection, collector_type)
    
    async def event_generator():
        """Generate SSE events from streaming chat."""
        conversation_id = None
        
        try:
            async for event in chat_service.achat_stream(
                query=request.message,
                conversation_id=request.conversation_id,
                top_k=request.top_k,
                user_id=token.user_id
            ):
                # Track conversation_id for collector type storage
                if event.get("type") == "done":
                    conversation_id = event.get("conversation_id")
                
                # Format as SSE
                yield f"data: {json.dumps(event)}\n\n"
            
            # Store collector type for new conversations
            if not request.conversation_id and request.collector_type and conversation_id:
                repos["conversation"].update_metadata(
                    conversation_id, 
                    {"collector_type": collector_type}
                )
            
            # Consume token after successful streaming
            repos["user"].consume_tokens(token.user_id, 1)
            
        except Exception as e:
            step_logger.error(f"[ChatAPI] Streaming error: {e}", exc_info=True)
            error_event = {"type": "error", "message": str(e)}
            yield f"data: {json.dumps(error_event)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@router.get(
    "/chat/{conversation_id}",
    response_model=ConversationResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Conversation History",
    description="Retrieve the message history for a conversation",
    responses={
        200: {
            "description": "Conversation history",
            "model": ConversationResponse
        },
        401: {
            "description": "Not authenticated"
        },
        404: {
            "description": "Conversation not found"
        }
    }
)
async def get_conversation(
    conversation_id: str,
    token: TokenPayload = Depends(get_current_user_from_token)
) -> ConversationResponse:
    """
    Get conversation history by ID.
    
    Args:
        conversation_id: Unique conversation identifier
        token: JWT token payload (injected)
    
    Returns:
        ConversationResponse with message history
    """
    step_logger.info(f"[ChatAPI] Getting conversation: {conversation_id}")
    
    repos = get_repositories()
    conversation = repos["conversation"].get_conversation(conversation_id, token.user_id)
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "ConversationNotFound",
                "message": f"Conversation '{conversation_id}' not found"
            }
        )
    
    # Convert messages to response format
    message_responses = []
    for msg in conversation.messages:
        citation_responses = [
            CitationResponse(
                cite_key=c.cite_key,
                display_text=c.display_text,
                article_id=c.article_id,
                article_number=c.article_number,
                normativa_title=c.normativa_title,
                article_path=c.article_path,
                score=c.score
            )
            for c in msg.citations
        ]
        
        message_responses.append(ConversationMessageResponse(
            role=msg.role,
            content=msg.content,
            citations=citation_responses,
            timestamp=msg.timestamp.isoformat()
        ))
    
    return ConversationResponse(
        id=conversation.id,
        messages=message_responses,
        created_at=conversation.created_at.isoformat(),
        updated_at=conversation.updated_at.isoformat()
    )


@router.delete(
    "/chat/{conversation_id}",
    response_model=DeleteResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete Conversation",
    description="Delete a conversation and all its messages",
    responses={
        200: {
            "description": "Conversation deleted successfully",
            "model": DeleteResponse
        },
        401: {
            "description": "Not authenticated"
        },
        404: {
            "description": "Conversation not found"
        }
    }
)
async def delete_conversation(
    conversation_id: str,
    token: TokenPayload = Depends(get_current_user_from_token)
) -> DeleteResponse:
    """
    Delete a conversation.
    
    Args:
        conversation_id: Unique conversation identifier
        token: JWT token payload (injected)
    
    Returns:
        DeleteResponse with success status
    """
    step_logger.info(f"[ChatAPI] Deleting conversation: {conversation_id}")
    
    repos = get_repositories()
    success = repos["conversation"].delete_conversation(conversation_id, token.user_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "ConversationNotFound",
                "message": f"Conversation '{conversation_id}' not found"
            }
        )
    
    return DeleteResponse(
        success=True,
        message=f"Conversation '{conversation_id}' deleted successfully"
    )


@router.post(
    "/chat/{conversation_id}/clear",
    response_model=DeleteResponse,
    status_code=status.HTTP_200_OK,
    summary="Clear Conversation",
    description="Clear all messages from a conversation but keep the conversation ID",
    responses={
        200: {
            "description": "Conversation cleared successfully",
            "model": DeleteResponse
        },
        401: {
            "description": "Not authenticated"
        },
        404: {
            "description": "Conversation not found"
        }
    }
)
async def clear_conversation(
    conversation_id: str,
    token: TokenPayload = Depends(get_current_user_from_token)
) -> DeleteResponse:
    """
    Clear all messages from a conversation.
    
    Args:
        conversation_id: Unique conversation identifier
        token: JWT token payload (injected)
    
    Returns:
        DeleteResponse with success status
    """
    step_logger.info(f"[ChatAPI] Clearing conversation: {conversation_id}")
    
    repos = get_repositories()
    success = repos["conversation"].clear_conversation(conversation_id, token.user_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "ConversationNotFound",
                "message": f"Conversation '{conversation_id}' not found"
            }
        )
    
    return DeleteResponse(
        success=True,
        message=f"Conversation '{conversation_id}' cleared successfully"
    )
