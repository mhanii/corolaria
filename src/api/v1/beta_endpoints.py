"""
Beta Testing API endpoints.
Provides endpoints for test mode status, feedback, and surveys.
"""
import json
import random
import yaml
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.v1.auth import get_current_user_from_token, TokenPayload
from src.api.v1.beta_schemas import (
    FeedbackRequest, FeedbackResponse, FeedbackType,
    SurveyRequest, SurveyResponse, SurveyQuestionsResponse,
    TestModeStatusResponse, ConfigMatrixResponse
)
from src.api.v1.chat_schemas import CitationResponse
from src.infrastructure.sqlite.base import init_database
from src.infrastructure.sqlite.user_repository import UserRepository
from src.infrastructure.sqlite.beta_repository import (
    FeedbackRepository, SurveyRepository
)
from src.infrastructure.sqlite.conversation_repository import ConversationRepository
from src.domain.models.beta_testing import (
    Feedback, FeedbackType as FeedbackTypeModel,
    ConfigMatrix, Survey
)
from src.observability.beta_tracing import annotate_response_feedback
from src.utils.logger import step_logger


# Create router
router = APIRouter(prefix="/beta", tags=["Beta Testing"])


def get_beta_config() -> dict:
    """Load beta testing configuration from config.yaml."""
    config_path = Path("config/config.yaml")
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            return config.get("beta_testing", {})
    return {}


def get_repositories():
    """Get SQLite repositories."""
    connection = init_database()
    return {
        "user": UserRepository(connection),
        "feedback": FeedbackRepository(connection),
        "survey": SurveyRepository(connection),
        "conversation": ConversationRepository(connection)
    }


# ============ Status Endpoint ============

@router.get(
    "/status",
    response_model=TestModeStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Beta Test Status",
    description="Get current test mode status and user token information"
)
async def get_test_status(
    token: TokenPayload = Depends(get_current_user_from_token)
) -> TestModeStatusResponse:
    """Get beta testing status for current user."""
    repos = get_repositories()
    config = get_beta_config()
    
    balance = repos["user"].get_token_balance(token.user_id)
    surveys_count = repos["survey"].count_user_surveys(token.user_id)
    
    return TestModeStatusResponse(
        test_mode_enabled=config.get("enabled", False),
        available_tokens=balance,
        requires_refill=balance <= 0,
        surveys_completed=surveys_count
    )


# ============ Survey Endpoints ============

@router.get(
    "/survey/questions",
    response_model=SurveyQuestionsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Survey Questions",
    description="Get the list of survey questions to answer"
)
async def get_survey_questions(
    token: TokenPayload = Depends(get_current_user_from_token)
) -> SurveyQuestionsResponse:
    """Get survey questions from config."""
    config = get_beta_config()
    questions = config.get("survey_questions", [
        "¿Qué tan útil fue la respuesta del asistente? (1-5)",
        "¿La respuesta citó fuentes legales de manera clara?",
        "¿Encontraste la información que buscabas?",
        "¿Qué tan fácil fue entender la respuesta?",
        "¿Recomendarías este asistente a un colega?"
    ])
    
    return SurveyQuestionsResponse(
        questions=questions,
        total_questions=len(questions)
    )


@router.post(
    "/survey",
    response_model=SurveyResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit Survey",
    description="Submit survey responses to refill tokens"
)
async def submit_survey(
    request: SurveyRequest,
    token: TokenPayload = Depends(get_current_user_from_token)
) -> SurveyResponse:
    """Submit survey and refill tokens."""
    repos = get_repositories()
    config = get_beta_config()
    
    # Check current balance - don't grant tokens if balance > 5
    current_balance = repos["user"].get_token_balance(token.user_id)
    if current_balance > 5:
        step_logger.info(f"[BetaAPI] User {token.username} has {current_balance} tokens, skipping refill")
        return SurveyResponse(
            success=True,
            tokens_granted=0,
            new_balance=current_balance,
            message=f"Encuesta registrada. Tu saldo actual ({current_balance} tokens) es suficiente."
        )
    
    tokens_to_grant = config.get("refill_tokens", 10)
    
    # Create survey record
    survey = Survey(
        user_id=token.user_id,
        responses=request.responses,
        tokens_granted=tokens_to_grant
    )
    
    if not repos["survey"].save_survey(survey):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "SurveyError", "message": "Failed to save survey"}
        )
    
    # Add tokens
    repos["user"].add_tokens(token.user_id, tokens_to_grant)
    new_balance = repos["user"].get_token_balance(token.user_id)
    
    step_logger.info(f"[BetaAPI] User {token.username} submitted survey, granted {tokens_to_grant} tokens")
    
    return SurveyResponse(
        success=True,
        tokens_granted=tokens_to_grant,
        new_balance=new_balance,
        message=f"¡Gracias! Se han añadido {tokens_to_grant} tokens a tu cuenta."
    )


# ============ Feedback Endpoint ============

@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit Feedback",
    description="Submit like/dislike/report feedback for a message"
)
async def submit_feedback(
    request: FeedbackRequest,
    token: TokenPayload = Depends(get_current_user_from_token)
) -> FeedbackResponse:
    """Submit feedback on a message with config matrix."""
    repos = get_repositories()
    
    # Get the message to extract config matrix
    conversation = repos["conversation"].get_conversation(
        request.conversation_id, 
        token.user_id
    )
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NotFound", "message": "Conversation not found"}
        )
    
    # Find the message and extract config from context_json or metadata
    config_data = {"model": "unknown", "temperature": 1.0, "top_k": 10, "collector_type": "rag"}
    
    for msg in conversation.messages:
        if hasattr(msg, 'id') and msg.id == request.message_id:
            # Try to extract config from message metadata or context
            if hasattr(msg, 'metadata') and msg.metadata:
                try:
                    meta = json.loads(msg.metadata) if isinstance(msg.metadata, str) else msg.metadata
                    config_data.update({
                        "model": meta.get("model", config_data["model"]),
                        "top_k": meta.get("top_k", config_data["top_k"]),
                        "collector_type": meta.get("collector_type", config_data["collector_type"]),
                        "context_reused": meta.get("context_reused", False)
                    })
                except:
                    pass
            break
    
    # Create feedback with config matrix
    feedback = Feedback(
        user_id=token.user_id,
        message_id=request.message_id,
        conversation_id=request.conversation_id,
        feedback_type=FeedbackTypeModel(request.feedback_type.value),
        config_matrix=ConfigMatrix.from_dict(config_data),
        comment=request.comment
    )
    
    if not repos["feedback"].save_feedback(feedback):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "FeedbackError", "message": "Failed to save feedback"}
        )
    
    step_logger.info(f"[BetaAPI] User {token.username} submitted {request.feedback_type.value} for message {request.message_id}")
    
    # Trace feedback to Phoenix
    annotate_response_feedback(
        conversation_id=request.conversation_id,
        message_id=request.message_id,
        feedback_type=request.feedback_type.value,
        config_matrix=config_data
    )
    
    return FeedbackResponse(
        id=feedback.id,
        success=True,
        message=f"Feedback '{request.feedback_type.value}' registrado. ¡Gracias!"
    )
