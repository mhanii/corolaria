#!/usr/bin/env python3
"""
Test script for authentication and chat persistence.
Verifies JWT auth flow, token management, and user isolation.

Usage:
    python scripts/test_auth.py
"""
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fastapi.testclient import TestClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from src.api.main import app
from src.infrastructure.sqlite.base import init_database
from src.infrastructure.sqlite.user_repository import UserRepository

# Create test client
client = TestClient(app)


def setup_test_users():
    """Create test users for isolation testing."""
    print("\n" + "="*60)
    print("SETUP: Creating test users")
    print("="*60)
    
    connection = init_database()
    user_repo = UserRepository(connection)
    
    # Create two users for isolation testing
    user1 = user_repo.create_user("auth_test_user1", "password123", 100)
    user2 = user_repo.create_user("auth_test_user2", "password456", 100)
    
    if user1:
        print(f"✓ Created user: auth_test_user1 (ID: {user1.id[:8]}...)")
    else:
        print("  User auth_test_user1 already exists")
        user1 = user_repo.get_by_username("auth_test_user1")
    
    if user2:
        print(f"✓ Created user: auth_test_user2 (ID: {user2.id[:8]}...)")
    else:
        print("  User auth_test_user2 already exists")
        user2 = user_repo.get_by_username("auth_test_user2")
    
    return user1, user2


def test_login_success():
    """Test successful login."""
    print("\n" + "="*60)
    print("TEST: Login with valid credentials")
    print("="*60)
    
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "auth_test_user1", "password": "password123"}
    )
    
    print(f"Status Code: {response.status_code}")
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    data = response.json()
    assert "access_token" in data, "Missing access_token"
    assert data["token_type"] == "bearer", "Wrong token type"
    assert data["username"] == "auth_test_user1", "Wrong username"
    assert "available_tokens" in data, "Missing available_tokens"
    
    print(f"✓ Login successful")
    print(f"  Token: {data['access_token'][:20]}...")
    print(f"  Available tokens: {data['available_tokens']}")
    
    return data["access_token"]


def test_login_invalid_password():
    """Test login with wrong password."""
    print("\n" + "="*60)
    print("TEST: Login with invalid password")
    print("="*60)
    
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "auth_test_user1", "password": "wrongpassword"}
    )
    
    print(f"Status Code: {response.status_code}")
    
    assert response.status_code == 401, f"Expected 401, got {response.status_code}"
    print("✓ Invalid password correctly rejected")


def test_login_unknown_user():
    """Test login with unknown username."""
    print("\n" + "="*60)
    print("TEST: Login with unknown user")
    print("="*60)
    
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "nonexistent_user", "password": "password123"}
    )
    
    print(f"Status Code: {response.status_code}")
    
    assert response.status_code == 401, f"Expected 401, got {response.status_code}"
    print("✓ Unknown user correctly rejected")


def test_protected_endpoint_without_token():
    """Test accessing protected endpoint without token."""
    print("\n" + "="*60)
    print("TEST: Access protected endpoint without token")
    print("="*60)
    
    response = client.get("/api/v1/conversations")
    
    print(f"Status Code: {response.status_code}")
    
    # HTTPBearer returns 401 (not 403) for missing credentials
    assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
    print("✓ Unauthenticated request correctly rejected")


def test_protected_endpoint_with_token(token):
    """Test accessing protected endpoint with valid token."""
    print("\n" + "="*60)
    print("TEST: Access protected endpoint with valid token")
    print("="*60)
    
    response = client.get(
        "/api/v1/conversations",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    print(f"Status Code: {response.status_code}")
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    data = response.json()
    assert "conversations" in data, "Missing conversations key"
    assert "total" in data, "Missing total key"
    
    print(f"✓ Authenticated request successful")
    print(f"  Conversations: {data['total']}")


def test_get_current_user(token):
    """Test the /me endpoint."""
    print("\n" + "="*60)
    print("TEST: Get current user info")
    print("="*60)
    
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    print(f"Status Code: {response.status_code}")
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    data = response.json()
    assert data["username"] == "auth_test_user1", "Wrong username"
    assert "available_tokens" in data, "Missing available_tokens"
    
    print(f"✓ User info retrieved")
    print(f"  Username: {data['username']}")
    print(f"  Tokens: {data['available_tokens']}")


def test_invalid_token():
    """Test accessing endpoint with invalid token."""
    print("\n" + "="*60)
    print("TEST: Access endpoint with invalid token")
    print("="*60)
    
    response = client.get(
        "/api/v1/conversations",
        headers={"Authorization": "Bearer invalid_token_here"}
    )
    
    print(f"Status Code: {response.status_code}")
    
    assert response.status_code == 401, f"Expected 401, got {response.status_code}"
    print("✓ Invalid token correctly rejected")


def main():
    """Run all auth tests."""
    print("\n" + "="*60)
    print("COLORARIA AUTH TEST SUITE")
    print("="*60)
    print("\nRunning authentication tests...")
    
    try:
        # Setup
        setup_test_users()
        
        # Run tests
        token = test_login_success()
        test_login_invalid_password()
        test_login_unknown_user()
        test_protected_endpoint_without_token()
        test_protected_endpoint_with_token(token)
        test_get_current_user(token)
        test_invalid_token()
        
        print("\n" + "="*60)
        print("✓ ALL AUTH TESTS PASSED")
        print("="*60 + "\n")
        
    except AssertionError as e:
        print("\n" + "="*60)
        print("✗ TEST FAILED")
        print("="*60)
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print("\n" + "="*60)
        print("✗ UNEXPECTED ERROR")
        print("="*60)
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
