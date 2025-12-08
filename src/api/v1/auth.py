"""
JWT authentication utilities.
Provides token creation, verification, and FastAPI dependencies.
"""
import os
import jwt
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.utils.logger import step_logger


# Security scheme for Swagger UI
security = HTTPBearer()

# JWT configuration
JWT_SECRET = os.getenv("JWT_SECRET", "coloraria-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "24"))


@dataclass
class TokenPayload:
    """Decoded JWT token payload."""
    user_id: str
    username: str
    exp: datetime


def create_access_token(user_id: str, username: str) -> str:
    """
    Create a JWT access token.
    
    Args:
        user_id: User ID to encode
        username: Username to encode
        
    Returns:
        Encoded JWT token string
    """
    expiry = datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS)
    
    payload = {
        "user_id": user_id,
        "username": username,
        "exp": expiry,
        "iat": datetime.utcnow()
    }
    
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    
    step_logger.info(f"[Auth] Created token for user: {username}")
    return token


def decode_token(token: str) -> Optional[TokenPayload]:
    """
    Decode and verify a JWT token.
    
    Args:
        token: JWT token string
        
    Returns:
        TokenPayload or None if invalid/expired
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        
        return TokenPayload(
            user_id=payload["user_id"],
            username=payload["username"],
            exp=datetime.fromtimestamp(payload["exp"])
        )
        
    except jwt.ExpiredSignatureError:
        step_logger.warning("[Auth] Token expired")
        return None
    except jwt.InvalidTokenError as e:
        step_logger.warning(f"[Auth] Invalid token: {e}")
        return None


def get_current_user_from_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> TokenPayload:
    """
    FastAPI dependency to get current user from JWT token.
    
    Raises HTTPException if token is invalid or expired.
    
    Args:
        credentials: HTTP Bearer credentials
        
    Returns:
        TokenPayload with user info
    """
    token = credentials.credentials
    payload = decode_token(token)
    
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "Unauthorized",
                "message": "Invalid or expired token"
            },
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return payload


def get_token_expiry_seconds() -> int:
    """Get token expiry in seconds (for response)."""
    return JWT_EXPIRY_HOURS * 3600
