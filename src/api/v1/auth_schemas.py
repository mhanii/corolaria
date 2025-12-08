"""
Pydantic schemas for Authentication API.
"""
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Request schema for login."""
    
    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Username"
    )
    password: str = Field(
        ...,
        min_length=6,
        description="Password"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "username": "tester1",
                "password": "securepassword"
            }
        }


class TokenResponse(BaseModel):
    """Response schema for successful login."""
    
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiry in seconds")
    user_id: str = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    available_tokens: int = Field(..., description="Remaining API call tokens")
    
    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 86400,
                "user_id": "abc123",
                "username": "tester1",
                "available_tokens": 1000
            }
        }


class UserInfoResponse(BaseModel):
    """Response schema for user info."""
    
    id: str = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    available_tokens: int = Field(..., description="Remaining API call tokens")
    created_at: str = Field(..., description="Account creation date")
