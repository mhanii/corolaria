"""
User repository for SQLite persistence.
Handles user CRUD operations with password hashing.
"""
import bcrypt
from datetime import datetime
from typing import Optional

from src.infrastructure.sqlite.connection import SQLiteConnection
from src.domain.models.user import User
from src.utils.logger import step_logger


class UserRepository:
    """
    Repository for user persistence in SQLite.
    
    Provides methods for creating users, authentication,
    and token management.
    """
    
    def __init__(self, connection: SQLiteConnection):
        """
        Initialize repository with connection manager.
        
        Args:
            connection: SQLite connection manager
        """
        self.connection = connection
    
    def create_user(
        self, 
        username: str, 
        password: str,
        available_tokens: int = 1000
    ) -> Optional[User]:
        """
        Create a new user with hashed password.
        
        Args:
            username: Unique username
            password: Plain text password (will be hashed)
            available_tokens: Initial token allocation
            
        Returns:
            Created User or None if username exists
        """
        # Check if username exists
        existing = self.get_by_username(username)
        if existing:
            step_logger.warning(f"[UserRepo] Username already exists: {username}")
            return None
        
        # Hash password
        password_hash = bcrypt.hashpw(
            password.encode('utf-8'), 
            bcrypt.gensalt()
        ).decode('utf-8')
        
        # Create user
        user = User(
            username=username,
            password_hash=password_hash,
            available_tokens=available_tokens
        )
        
        # Insert into database
        self.connection.execute(
            """
            INSERT INTO users (id, username, password_hash, available_tokens, created_at, is_active)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user.id,
                user.username,
                user.password_hash,
                user.available_tokens,
                user.created_at.isoformat(),
                1 if user.is_active else 0
            )
        )
        
        step_logger.info(f"[UserRepo] Created user: {username} (tokens: {available_tokens})")
        return user
    
    def get_by_username(self, username: str) -> Optional[User]:
        """
        Get user by username.
        
        Args:
            username: Username to look up
            
        Returns:
            User or None if not found
        """
        row = self.connection.fetchone(
            "SELECT * FROM users WHERE username = ?",
            (username,)
        )
        
        if row is None:
            return None
        
        return self._row_to_user(row)
    
    def get_by_id(self, user_id: str) -> Optional[User]:
        """
        Get user by ID.
        
        Args:
            user_id: User ID to look up
            
        Returns:
            User or None if not found
        """
        row = self.connection.fetchone(
            "SELECT * FROM users WHERE id = ?",
            (user_id,)
        )
        
        if row is None:
            return None
        
        return self._row_to_user(row)
    
    def verify_password(self, user: User, password: str) -> bool:
        """
        Verify password against stored hash.
        
        Args:
            user: User to verify
            password: Plain text password to check
            
        Returns:
            True if password matches
        """
        return bcrypt.checkpw(
            password.encode('utf-8'),
            user.password_hash.encode('utf-8')
        )
    
    def consume_tokens(self, user_id: str, count: int = 1) -> bool:
        """
        Consume tokens for a user (for rate limiting).
        
        Args:
            user_id: User ID
            count: Number of tokens to consume
            
        Returns:
            True if tokens were consumed, False if insufficient
        """
        # Get current tokens
        row = self.connection.fetchone(
            "SELECT available_tokens FROM users WHERE id = ?",
            (user_id,)
        )
        
        if row is None:
            return False
        
        current_tokens = row['available_tokens']
        
        if current_tokens < count:
            step_logger.warning(f"[UserRepo] User {user_id} has insufficient tokens: {current_tokens}")
            return False
        
        # Decrement tokens
        self.connection.execute(
            "UPDATE users SET available_tokens = available_tokens - ? WHERE id = ?",
            (count, user_id)
        )
        
        step_logger.debug(f"[UserRepo] User {user_id} consumed {count} token(s). Remaining: {current_tokens - count}")
        return True
    
    def get_token_balance(self, user_id: str) -> int:
        """
        Get current token balance for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            Available tokens or 0 if user not found
        """
        row = self.connection.fetchone(
            "SELECT available_tokens FROM users WHERE id = ?",
            (user_id,)
        )
        
        return row['available_tokens'] if row else 0
    
    def add_tokens(self, user_id: str, count: int) -> bool:
        """
        Add tokens to a user's balance.
        
        Args:
            user_id: User ID
            count: Number of tokens to add
            
        Returns:
            True if successful
        """
        result = self.connection.execute(
            "UPDATE users SET available_tokens = available_tokens + ? WHERE id = ?",
            (count, user_id)
        )
        
        return result.rowcount > 0
    
    def _row_to_user(self, row) -> User:
        """Convert database row to User object."""
        return User(
            id=row['id'],
            username=row['username'],
            password_hash=row['password_hash'],
            available_tokens=row['available_tokens'],
            created_at=datetime.fromisoformat(row['created_at']),
            is_active=bool(row['is_active'])
        )
