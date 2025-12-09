"""
Pydantic schemas for Chat API v1 request and response models.
"""
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class CollectorType(str, Enum):
    """Available context collector types for RAG retrieval."""
    RAG = "rag"
    QRAG = "qrag"


class ChatRequest(BaseModel):
    """Request schema for chat endpoint."""
    
    message: str = Field(
        ...,
        min_length=1,
        description="The user's message or question",
        examples=["¿Qué dice el artículo 14 de la Constitución?"]
    )
    conversation_id: Optional[str] = Field(
        default=None,
        description="Optional conversation ID for multi-turn chat"
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of sources to retrieve (1-20)"
    )
    collector_type: Optional[CollectorType] = Field(
        default=None,
        description="Context collector type: 'rag' (default) or 'qrag' (query-optimized). Only applies to first message."
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "¿Qué establece la Constitución sobre la igualdad?",
                "conversation_id": None,
                "top_k": 5,
                "collector_type": None
            }
        }


class CitationResponse(BaseModel):
    """Schema for citation in response."""
    
    cite_key: str = Field(..., description="Citation key like 'art_14_ce_abc123'")
    display_text: str = Field(default="", description="Text shown in the citation (e.g., 'Artículo 14')")
    article_id: str = Field(..., description="Unique article identifier")
    article_number: str = Field(..., description="Article number (e.g., 'Artículo 14')")
    normativa_title: str = Field(..., description="Title of the regulation")
    article_path: str = Field(default="", description="Hierarchical path (e.g., 'Título I')")
    score: float = Field(..., description="Retrieval similarity score")
    
    class Config:
        json_schema_extra = {
            "example": {
                "cite_key": "art_14_ce_abc123",
                "display_text": "Artículo 14",
                "article_id": "abc123",
                "article_number": "Artículo 14",
                "normativa_title": "Constitución Española de 1978",
                "article_path": "Título I, Capítulo Segundo",
                "score": 0.89
            }
        }


class ChatResponse(BaseModel):
    """Response schema for chat endpoint."""
    
    response: str = Field(..., description="AI assistant's response with inline semantic citations")
    conversation_id: str = Field(..., description="Conversation ID for follow-up messages")
    citations: List[CitationResponse] = Field(
        default_factory=list,
        description="List of citations referenced in the response"
    )
    execution_time_ms: float = Field(..., description="Total processing time in milliseconds")
    
    class Config:
        json_schema_extra = {
            "example": {
                "response": "El [cite:art_14_ce_abc123]Artículo 14 de la Constitución Española[/cite] establece que los españoles son iguales ante la ley.",
                "conversation_id": "abc123-def456",
                "citations": [
                    {
                        "cite_key": "art_14_ce_abc123",
                        "display_text": "Artículo 14 de la Constitución Española",
                        "article_id": "abc123",
                        "article_number": "Artículo 14",
                        "normativa_title": "Constitución Española de 1978",
                        "article_path": "Título I",
                        "score": 0.92
                    }
                ],
                "execution_time_ms": 1250.5
            }
        }


class ConversationMessageResponse(BaseModel):
    """Schema for a message in conversation history."""
    
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")
    citations: List[CitationResponse] = Field(
        default_factory=list,
        description="Citations for assistant messages"
    )
    timestamp: str = Field(..., description="Message timestamp (ISO format)")


class ConversationResponse(BaseModel):
    """Response schema for conversation retrieval."""
    
    id: str = Field(..., description="Conversation ID")
    messages: List[ConversationMessageResponse] = Field(
        default_factory=list,
        description="List of messages in the conversation"
    )
    created_at: str = Field(..., description="Conversation creation time (ISO format)")
    updated_at: str = Field(..., description="Last update time (ISO format)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "abc123-def456",
                "messages": [
                    {
                        "role": "user",
                        "content": "¿Qué dice el artículo 14?",
                        "citations": [],
                        "timestamp": "2024-01-15T10:30:00"
                    },
                    {
                        "role": "assistant",
                        "content": "El artículo 14 establece...",
                        "citations": [],
                        "timestamp": "2024-01-15T10:30:05"
                    }
                ],
                "created_at": "2024-01-15T10:30:00",
                "updated_at": "2024-01-15T10:30:05"
            }
        }


class DeleteResponse(BaseModel):
    """Response schema for delete operations."""
    
    success: bool = Field(..., description="Whether the operation succeeded")
    message: str = Field(..., description="Status message")


# ============ Streaming Event Schemas ============

class StreamChunkEvent(BaseModel):
    """Schema for streaming text chunk event."""
    
    type: str = Field(default="chunk", description="Event type")
    content: str = Field(..., description="Partial response text")


class StreamCitationsEvent(BaseModel):
    """Schema for streaming citations event."""
    
    type: str = Field(default="citations", description="Event type")
    citations: List[CitationResponse] = Field(..., description="List of citations used")


class StreamDoneEvent(BaseModel):
    """Schema for streaming completion event."""
    
    type: str = Field(default="done", description="Event type")
    conversation_id: str = Field(..., description="Conversation ID")
    execution_time_ms: float = Field(..., description="Total execution time in ms")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")


class StreamErrorEvent(BaseModel):
    """Schema for streaming error event."""
    
    type: str = Field(default="error", description="Event type")
    message: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Error details")

