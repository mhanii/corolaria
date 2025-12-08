"""
User domain model.
Represents an authenticated user with token-based rate limiting.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import uuid


@dataclass
class User:
    """
    User model for authentication and rate limiting.
    
    Attributes:
        id: Unique user identifier
        username: Login username (unique)
        password_hash: Bcrypt hashed password
        available_tokens: Remaining API call tokens (decremented on each chat)
        created_at: Account creation timestamp
        is_active: Whether user account is active
    """
    username: str
    password_hash: str
    available_tokens: int = 1000  # Default token limit
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.now)
    is_active: bool = True
    
    def has_tokens(self) -> bool:
        """Check if user has remaining tokens."""
        return self.available_tokens > 0
    
    def consume_token(self, count: int = 1) -> bool:
        """
        Consume tokens for an API call.
        
        Args:
            count: Number of tokens to consume
            
        Returns:
            True if tokens were consumed, False if insufficient
        """
        if self.available_tokens >= count:
            self.available_tokens -= count
            return True
        return False
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization (excluding password)."""
        return {
            "id": self.id,
            "username": self.username,
            "available_tokens": self.available_tokens,
            "created_at": self.created_at.isoformat(),
            "is_active": self.is_active
        }
