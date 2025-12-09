"""
Conversation models.
Data structures for multi-turn chat conversations.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

from src.domain.models.citation import Citation


@dataclass
class ConversationMessage:
    """
    Represents a message in a conversation.
    Includes role, content, and optional citations.
    """
    role: str  # "user" | "assistant" | "system"
    content: str
    citations: List[Citation] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    context_json: Optional[str] = None  # Serialized context chunks used for this message
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "role": self.role,
            "content": self.content,
            "citations": [c.to_summary_dict() for c in self.citations],
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "has_context": self.context_json is not None
        }
    
    def to_llm_format(self) -> Dict[str, str]:
        """Convert to format expected by LLM APIs (role + content only)."""
        return {"role": self.role, "content": self.content}


@dataclass
class Conversation:
    """
    Represents a multi-turn conversation.
    Tracks messages and metadata for context retention.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    messages: List[ConversationMessage] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_message(self, message: ConversationMessage) -> None:
        """Add a message to the conversation."""
        self.messages.append(message)
        self.updated_at = datetime.now()
    
    def add_user_message(self, content: str) -> ConversationMessage:
        """Add a user message and return it."""
        msg = ConversationMessage(role="user", content=content)
        self.add_message(msg)
        return msg
    
    def add_assistant_message(
        self, 
        content: str, 
        citations: Optional[List[Citation]] = None
    ) -> ConversationMessage:
        """Add an assistant message with optional citations."""
        msg = ConversationMessage(
            role="assistant", 
            content=content, 
            citations=citations or []
        )
        self.add_message(msg)
        return msg
    
    def get_history(self, max_messages: Optional[int] = None) -> List[ConversationMessage]:
        """
        Get conversation history.
        
        Args:
            max_messages: Maximum number of messages to return (from end)
            
        Returns:
            List of messages
        """
        if max_messages is None:
            return self.messages.copy()
        return self.messages[-max_messages:] if len(self.messages) > max_messages else self.messages.copy()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "messages": [m.to_dict() for m in self.messages],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata
        }
    
    def clear(self) -> None:
        """Clear all messages from the conversation."""
        self.messages = []
        self.updated_at = datetime.now()
