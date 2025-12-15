"""
MariaDB Beta Testing Repository.
Implements feedback and survey persistence with SQLAlchemy-compatible queries.
"""
import json
from datetime import datetime
from typing import List

from src.infrastructure.database.interface import DatabaseConnection
from src.domain.models.beta_testing import (
    Feedback, FeedbackType, ConfigMatrix, Survey
)
from src.utils.logger import step_logger


class MariaDBFeedbackRepository:
    """Repository for feedback persistence in MariaDB."""
    
    def __init__(self, connection: DatabaseConnection):
        self.connection = connection
    
    def save_feedback(self, feedback: Feedback) -> bool:
        """Save feedback with config matrix."""
        try:
            self.connection.execute(
                """
                INSERT INTO feedback (
                    id, user_id, message_id, conversation_id, 
                    feedback_type, comment, config_matrix, created_at
                ) VALUES (:p0, :p1, :p2, :p3, :p4, :p5, :p6, :p7)
                """,
                (
                    feedback.id,
                    feedback.user_id,
                    feedback.message_id,
                    feedback.conversation_id,
                    feedback.feedback_type.value,
                    feedback.comment,
                    json.dumps(feedback.config_matrix.to_dict()),
                    feedback.created_at
                )
            )
            step_logger.info(f"[BetaRepo] Saved feedback {feedback.id}")
            return True
        except Exception as e:
            step_logger.error(f"[BetaRepo] Failed to save feedback: {e}")
            return False
    
    def get_feedback_by_message(self, message_id: int) -> List[Feedback]:
        """Get all feedback for a message."""
        rows = self.connection.fetchall(
            "SELECT * FROM feedback WHERE message_id = :p0",
            (message_id,)
        )
        return [self._row_to_feedback(r) for r in rows]
    
    def get_user_feedback(self, user_id: str) -> List[Feedback]:
        """Get all feedback from a user."""
        rows = self.connection.fetchall(
            "SELECT * FROM feedback WHERE user_id = :p0 ORDER BY created_at DESC",
            (user_id,)
        )
        return [self._row_to_feedback(r) for r in rows]
    
    def _row_to_feedback(self, row: dict) -> Feedback:
        """Convert DB row to Feedback object."""
        created_at = row['created_at']
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        
        config_matrix = row['config_matrix']
        if isinstance(config_matrix, str):
            config_matrix = json.loads(config_matrix)
        
        return Feedback(
            id=row['id'],
            user_id=row['user_id'],
            message_id=row['message_id'],
            conversation_id=row['conversation_id'],
            feedback_type=FeedbackType(row['feedback_type']),
            config_matrix=ConfigMatrix.from_dict(config_matrix),
            comment=row['comment'],
            created_at=created_at
        )


class MariaDBSurveyRepository:
    """Repository for survey persistence in MariaDB."""
    
    def __init__(self, connection: DatabaseConnection):
        self.connection = connection
    
    def save_survey(self, survey: Survey) -> bool:
        """Save a survey response."""
        try:
            self.connection.execute(
                """
                INSERT INTO surveys (id, user_id, responses, tokens_granted, submitted_at)
                VALUES (:p0, :p1, :p2, :p3, :p4)
                """,
                (
                    survey.id,
                    survey.user_id,
                    json.dumps(survey.responses),
                    survey.tokens_granted,
                    survey.submitted_at
                )
            )
            step_logger.info(f"[BetaRepo] Saved survey {survey.id}")
            return True
        except Exception as e:
            step_logger.error(f"[BetaRepo] Failed to save survey: {e}")
            return False
    
    def get_user_surveys(self, user_id: str) -> List[Survey]:
        """Get all surveys from a user."""
        rows = self.connection.fetchall(
            "SELECT * FROM surveys WHERE user_id = :p0 ORDER BY submitted_at DESC",
            (user_id,)
        )
        return [self._row_to_survey(r) for r in rows]
    
    def count_user_surveys(self, user_id: str) -> int:
        """Count total surveys submitted by user."""
        row = self.connection.fetchone(
            "SELECT COUNT(*) as count FROM surveys WHERE user_id = :p0",
            (user_id,)
        )
        return row['count'] if row else 0
    
    def _row_to_survey(self, row: dict) -> Survey:
        """Convert DB row to Survey object."""
        submitted_at = row['submitted_at']
        if isinstance(submitted_at, str):
            submitted_at = datetime.fromisoformat(submitted_at)
        
        responses = row['responses']
        if isinstance(responses, str):
            responses = json.loads(responses)
        
        return Survey(
            id=row['id'],
            user_id=row['user_id'],
            responses=responses,
            tokens_granted=row['tokens_granted'],
            submitted_at=submitted_at
        )
