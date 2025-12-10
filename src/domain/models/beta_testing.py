"""
Beta Testing domain models.
Models for feedback and surveys.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
import uuid


class FeedbackType(str, Enum):
    """Types of feedback a user can submit."""
    LIKE = "like"
    DISLIKE = "dislike"
    REPORT = "report"


@dataclass
class ConfigMatrix:
    """
    Configuration parameters used to generate a response.
    Captures all variable settings for analysis.
    """
    model: str
    temperature: float
    top_k: int
    collector_type: str
    prompt_version: str = "1.0"
    context_reused: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            "model": self.model,
            "temperature": self.temperature,
            "top_k": self.top_k,
            "collector_type": self.collector_type,
            "prompt_version": self.prompt_version,
            "context_reused": self.context_reused,
            **self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConfigMatrix":
        """Deserialize from dictionary."""
        known_keys = {"model", "temperature", "top_k", "collector_type", 
                      "prompt_version", "context_reused"}
        metadata = {k: v for k, v in data.items() if k not in known_keys}
        return cls(
            model=data.get("model", ""),
            temperature=data.get("temperature", 1.0),
            top_k=data.get("top_k", 10),
            collector_type=data.get("collector_type", "rag"),
            prompt_version=data.get("prompt_version", "1.0"),
            context_reused=data.get("context_reused", False),
            metadata=metadata
        )


@dataclass
class Feedback:
    """
    User feedback on a message response.
    Captures the configuration matrix for analysis.
    """
    user_id: str
    message_id: int
    conversation_id: str
    feedback_type: FeedbackType
    config_matrix: ConfigMatrix
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    comment: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize for storage/response."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "message_id": self.message_id,
            "conversation_id": self.conversation_id,
            "feedback_type": self.feedback_type.value,
            "config_matrix": self.config_matrix.to_dict(),
            "comment": self.comment,
            "created_at": self.created_at.isoformat()
        }


@dataclass
class Survey:
    """
    5-question survey for token refill.
    """
    user_id: str
    responses: List[str]
    tokens_granted: int
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    submitted_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize for storage/response."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "responses": self.responses,
            "tokens_granted": self.tokens_granted,
            "submitted_at": self.submitted_at.isoformat()
        }
