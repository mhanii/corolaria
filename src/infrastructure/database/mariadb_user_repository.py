"""
MariaDB User Repository.
Implements user persistence with SQLAlchemy-compatible queries.
"""
import bcrypt
import os
from datetime import datetime
from typing import Optional

from src.infrastructure.database.interface import DatabaseConnection
from src.domain.models.user import User
from src.utils.logger import step_logger


class MariaDBUserRepository:
    """
    Repository for user persistence in MariaDB.
    
    Uses named parameters (:pN) for SQLAlchemy text() queries.
    """
    
    def __init__(self, connection: DatabaseConnection):
        """Initialize with database connection."""
        self.connection = connection
    
    def create_user(
        self, 
        username: str, 
        password: str,
        available_tokens: int = 1000
    ) -> Optional[User]:
        """Create a new user with hashed password."""
        # Check if username exists
        existing = self.get_by_username(username)
        if existing:
            step_logger.warning(f"[UserRepo] Username already exists: {username}")
            return None
        
        # Hash password - handle both bcrypt and python-bcrypt versions
        password_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt()
        try:
            # Modern bcrypt (>=4.0.0) expects bytes
            hashed = bcrypt.hashpw(password_bytes, salt)
        except TypeError:
            # Old python-bcrypt expects str
            hashed = bcrypt.hashpw(password, salt)
        
        # Ensure we have a string for storage
        password_hash = hashed.decode('utf-8') if isinstance(hashed, bytes) else hashed
        
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
            VALUES (:p0, :p1, :p2, :p3, :p4, :p5)
            """,
            (
                user.id,
                user.username,
                user.password_hash,
                user.available_tokens,
                user.created_at,
                1 if user.is_active else 0
            )
        )
        
        step_logger.info(f"[UserRepo] Created user: {username} (tokens: {available_tokens})")
        return user
    
    def get_by_username(self, username: str) -> Optional[User]:
        """Get user by username."""
        row = self.connection.fetchone(
            "SELECT * FROM users WHERE username = :p0",
            (username,)
        )
        
        if row is None:
            return None
        
        return self._row_to_user(row)
    
    def get_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID."""
        row = self.connection.fetchone(
            "SELECT * FROM users WHERE id = :p0",
            (user_id,)
        )
        
        if row is None:
            return None
        
        return self._row_to_user(row)
    
    def verify_password(self, user: User, password: str) -> bool:
        """Verify password against stored hash."""
        return bcrypt.checkpw(
            password.encode('utf-8'),
            user.password_hash.encode('utf-8')
        )
    
    def consume_tokens(self, user_id: str, count: int = 1) -> bool:
        """
        Atomically consume tokens (concurrent-safe).
        
        Uses UPDATE with WHERE clause to prevent race conditions.
        """
        result = self.connection.execute(
            """
            UPDATE users 
            SET available_tokens = available_tokens - :p0 
            WHERE id = :p1 AND available_tokens >= :p0
            """,
            (count, user_id)
        )
        
        # Check if update affected any rows
        if result.rowcount > 0:
            step_logger.debug(f"[UserRepo] User {user_id} consumed {count} token(s)")
            return True
        
        step_logger.warning(f"[UserRepo] User {user_id} has insufficient tokens")
        return False
    
    def get_token_balance(self, user_id: str) -> int:
        """Get current token balance for a user."""
        row = self.connection.fetchone(
            "SELECT available_tokens FROM users WHERE id = :p0",
            (user_id,)
        )
        
        return row['available_tokens'] if row else 0
    
    def add_tokens(self, user_id: str, count: int) -> bool:
        """Add tokens to a user's balance."""
        result = self.connection.execute(
            "UPDATE users SET available_tokens = available_tokens + :p0 WHERE id = :p1",
            (count, user_id)
        )
        
        return result.rowcount > 0
    
    def _row_to_user(self, row: dict) -> User:
        """Convert database row to User object."""
        created_at = row['created_at']
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        
        return User(
            id=row['id'],
            username=row['username'],
            password_hash=row['password_hash'],
            available_tokens=row['available_tokens'],
            created_at=created_at,
            is_active=bool(row['is_active'])
        )
