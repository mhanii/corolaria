"""
Authentication API endpoints.
Provides login endpoint (no registration - accounts created via CLI).
"""
from fastapi import APIRouter, HTTPException, status, Depends

from src.api.v1.auth_schemas import LoginRequest, TokenResponse, UserInfoResponse
from src.api.v1.auth import (
    create_access_token, 
    get_token_expiry_seconds,
    get_current_user_from_token,
    TokenPayload
)
from src.infrastructure.sqlite.base import init_database
from src.infrastructure.sqlite.user_repository import UserRepository
from src.utils.logger import step_logger


# Create router
router = APIRouter(prefix="/auth", tags=["Authentication"])


def get_user_repository() -> UserRepository:
    """Get user repository dependency."""
    connection = init_database()
    return UserRepository(connection)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Login",
    description="Authenticate with username and password to get a JWT token",
    responses={
        200: {
            "description": "Successful login",
            "model": TokenResponse
        },
        401: {
            "description": "Invalid credentials"
        }
    }
)
async def login(
    request: LoginRequest,
    user_repo: UserRepository = Depends(get_user_repository)
) -> TokenResponse:
    """
    Authenticate user and return JWT token.
    
    Args:
        request: Login credentials
        user_repo: User repository (injected)
        
    Returns:
        JWT token and user info
    """
    step_logger.info(f"[AuthAPI] Login attempt: {request.username}")
    
    # Get user by username
    user = user_repo.get_by_username(request.username)
    
    if user is None:
        step_logger.warning(f"[AuthAPI] User not found: {request.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "Unauthorized",
                "message": "Invalid username or password"
            }
        )
    
    # Verify password
    if not user_repo.verify_password(user, request.password):
        step_logger.warning(f"[AuthAPI] Invalid password for: {request.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "Unauthorized", 
                "message": "Invalid username or password"
            }
        )
    
    # Check if user is active
    if not user.is_active:
        step_logger.warning(f"[AuthAPI] Inactive user: {request.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "Unauthorized",
                "message": "Account is disabled"
            }
        )
    
    # Create token
    token = create_access_token(user.id, user.username)
    
    step_logger.info(f"[AuthAPI] Login successful: {request.username}")
    
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=get_token_expiry_seconds(),
        user_id=user.id,
        username=user.username,
        available_tokens=user.available_tokens
    )


@router.get(
    "/me",
    response_model=UserInfoResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Current User",
    description="Get information about the currently authenticated user",
    responses={
        200: {
            "description": "User info",
            "model": UserInfoResponse
        },
        401: {
            "description": "Not authenticated"
        }
    }
)
async def get_current_user(
    token_payload: TokenPayload = Depends(get_current_user_from_token),
    user_repo: UserRepository = Depends(get_user_repository)
) -> UserInfoResponse:
    """
    Get current user information.
    
    Args:
        token_payload: Decoded JWT token (injected)
        user_repo: User repository (injected)
        
    Returns:
        Current user info
    """
    user = user_repo.get_by_id(token_payload.user_id)
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "Unauthorized",
                "message": "User not found"
            }
        )
    
    return UserInfoResponse(
        id=user.id,
        username=user.username,
        available_tokens=user.available_tokens,
        created_at=user.created_at.isoformat()
    )
