"""
Chat API v1 endpoints.
RESTful endpoints for AI chatbot with RAG-based citations.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from src.api.v1.chat_schemas import (
    ChatRequest,
    ChatResponse,
    CitationResponse,
    ConversationResponse,
    ConversationMessageResponse,
    DeleteResponse
)
from src.api.v1.dependencies import (
    get_neo4j_connection,
    get_embedding_provider,
    get_chat_service,
    get_conversation_service
)
from src.domain.services.chat_service import ChatService
from src.domain.services.conversation_service import ConversationService
from src.utils.logger import step_logger

# Create router for chat endpoints
router = APIRouter()


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
        500: {
            "description": "Internal server error (LLM or retrieval failure)"
        }
    }
)
async def chat(
    request: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service)
) -> ChatResponse:
    """
    Process a chat message and return AI response with citations.
    
    This endpoint:
    1. Retrieves relevant legal articles using semantic search
    2. Generates response using LLM with context
    3. Returns response with inline citations [1], [2], etc.
    
    Args:
        request: Chat request with message and optional conversation_id
        chat_service: Chat service (injected)
    
    Returns:
        ChatResponse with AI response and source citations
    """
    step_logger.info(f"[ChatAPI] Received chat request: message='{request.message[:50]}...'")
    
    try:
        # Process chat through service
        result = await chat_service.achat(
            query=request.message,
            conversation_id=request.conversation_id,
            top_k=request.top_k
        )
        
        # Convert citations to response format
        citation_responses = [
            CitationResponse(
                index=c.index,
                article_id=c.article_id,
                article_number=c.article_number,
                normativa_title=c.normativa_title,
                article_path=c.article_path,
                score=c.score
            )
            for c in result.citations
        ]
        
        step_logger.info(f"[ChatAPI] Response generated: {len(citation_responses)} citations")
        
        return ChatResponse(
            response=result.response,
            conversation_id=result.conversation_id,
            citations=citation_responses,
            execution_time_ms=result.execution_time_ms
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
        404: {
            "description": "Conversation not found"
        }
    }
)
async def get_conversation(
    conversation_id: str,
    conversation_service: ConversationService = Depends(get_conversation_service)
) -> ConversationResponse:
    """
    Get conversation history by ID.
    
    Args:
        conversation_id: Unique conversation identifier
        conversation_service: Conversation service (injected)
    
    Returns:
        ConversationResponse with message history
    """
    step_logger.info(f"[ChatAPI] Getting conversation: {conversation_id}")
    
    conversation = conversation_service.get_conversation(conversation_id)
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "ConversationNotFound",
                "message": f"Conversation '{conversation_id}' not found or expired"
            }
        )
    
    # Convert messages to response format
    message_responses = []
    for msg in conversation.messages:
        citation_responses = [
            CitationResponse(
                index=c.index,
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
        404: {
            "description": "Conversation not found"
        }
    }
)
async def delete_conversation(
    conversation_id: str,
    conversation_service: ConversationService = Depends(get_conversation_service)
) -> DeleteResponse:
    """
    Delete a conversation.
    
    Args:
        conversation_id: Unique conversation identifier
        conversation_service: Conversation service (injected)
    
    Returns:
        DeleteResponse with success status
    """
    step_logger.info(f"[ChatAPI] Deleting conversation: {conversation_id}")
    
    success = conversation_service.delete_conversation(conversation_id)
    
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
        404: {
            "description": "Conversation not found"
        }
    }
)
async def clear_conversation(
    conversation_id: str,
    conversation_service: ConversationService = Depends(get_conversation_service)
) -> DeleteResponse:
    """
    Clear all messages from a conversation.
    
    Args:
        conversation_id: Unique conversation identifier
        conversation_service: Conversation service (injected)
    
    Returns:
        DeleteResponse with success status
    """
    step_logger.info(f"[ChatAPI] Clearing conversation: {conversation_id}")
    
    success = conversation_service.clear_conversation(conversation_id)
    
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
