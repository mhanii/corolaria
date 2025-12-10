"""
Pydantic schemas for Beta Testing API endpoints.
"""
from enum import Enum
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field

from src.api.v1.chat_schemas import CitationResponse


class FeedbackType(str, Enum):
    """Types of feedback."""
    LIKE = "like"
    DISLIKE = "dislike"
    REPORT = "report"


# ============ Request Schemas ============

class FeedbackRequest(BaseModel):
    """Request to submit feedback on a message."""
    message_id: int = Field(..., description="ID of the message to provide feedback on")
    conversation_id: str = Field(..., description="ID of the conversation")
    feedback_type: FeedbackType = Field(..., description="Type of feedback: like, dislike, or report")
    comment: Optional[str] = Field(default=None, max_length=1000, description="Optional comment")
    
    class Config:
        json_schema_extra = {
            "example": {
                "message_id": 42,
                "conversation_id": "abc123-def456",
                "feedback_type": "like",
                "comment": None
            }
        }


class SurveyRequest(BaseModel):
    """Request to submit a 5-question survey for token refill."""
    responses: List[str] = Field(
        ..., 
        min_length=5, 
        max_length=5,
        description="5 survey responses (one per question)"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "responses": [
                    "5 - Muy útil",
                    "Sí, las citas fueron claras",
                    "Sí, encontré lo que buscaba",
                    "4 - Bastante fácil",
                    "Sí, lo recomendaría"
                ]
            }
        }



# ============ Response Schemas ============

class FeedbackResponse(BaseModel):
    """Response after submitting feedback."""
    id: str = Field(..., description="Feedback ID")
    success: bool = Field(..., description="Whether feedback was saved")
    message: str = Field(default="Feedback recorded", description="Status message")


class SurveyResponse(BaseModel):
    """Response after submitting survey."""
    success: bool = Field(..., description="Whether survey was saved")
    tokens_granted: int = Field(..., description="Tokens added to balance")
    new_balance: int = Field(..., description="New token balance")
    message: str = Field(default="Survey submitted successfully", description="Status message")


class SurveyQuestionsResponse(BaseModel):
    """Response containing survey questions."""
    questions: List[str] = Field(..., description="List of survey questions")
    total_questions: int = Field(..., description="Number of questions to answer")



class TestModeStatusResponse(BaseModel):
    """Response with test mode status and user state."""
    test_mode_enabled: bool = Field(..., description="Whether beta test mode is active")
    available_tokens: int = Field(..., description="User's current token balance")
    requires_refill: bool = Field(..., description="Whether user needs to complete survey for tokens")
    surveys_completed: int = Field(default=0, description="Number of surveys user has completed")
    
    class Config:
        json_schema_extra = {
            "example": {
                "test_mode_enabled": True,
                "available_tokens": 5,
                "requires_refill": False,
                "surveys_completed": 2
            }
        }


class ConfigMatrixResponse(BaseModel):
    """Configuration matrix for a response (exposed in test mode)."""
    model: str = Field(..., description="LLM model used")
    temperature: float = Field(..., description="Temperature setting")
    top_k: int = Field(..., description="Number of chunks retrieved")
    collector_type: str = Field(..., description="Context collector type")
    prompt_version: str = Field(default="1.0", description="Prompt template version")
    context_reused: bool = Field(default=False, description="Whether context was reused from history")
