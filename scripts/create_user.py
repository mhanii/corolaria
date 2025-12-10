#!/usr/bin/env python3
"""
CLI script to create user accounts.
Used to create tester accounts since registration is disabled.

Usage:
    python scripts/create_user.py <username> <password> [--tokens N]
    
Examples:
    python scripts/create_user.py tester1 securepass123
    python scripts/create_user.py admin adminpass --tokens 5000
"""
import sys
import os
import argparse

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.infrastructure.sqlite.base import init_database
from src.infrastructure.sqlite.user_repository import UserRepository


def main():
    parser = argparse.ArgumentParser(
        description="Create a user account for Coloraria API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/create_user.py tester1 securepass123
    python scripts/create_user.py admin adminpass --tokens 5000
        """
    )
    
    parser.add_argument("username", help="Username (3-50 characters)")
    parser.add_argument("password", help="Password (minimum 6 characters)")
    parser.add_argument(
        "--tokens", "-t",
        type=int,
        default=None,
        help="Initial token allocation (default: 1000, or 15 for test users)"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Create as test user with beta testing token allocation (15 tokens)"
    )

    
    args = parser.parse_args()
    
    # Validate input
    if len(args.username) < 3:
        print("Error: Username must be at least 3 characters")
        sys.exit(1)
    
    if len(args.password) < 6:
        print("Error: Password must be at least 6 characters")
        sys.exit(1)
    
    # Initialize database
    print("Initializing database...")
    connection = init_database()
    
    # Create repository
    user_repo = UserRepository(connection)
    
    # Determine token allocation
    if args.tokens is not None:
        token_count = args.tokens
    elif args.test:
        token_count = 15  # Beta testing initial tokens
        print("(Test user mode - using 15 tokens)")
    else:
        token_count = 1000  # Default for regular users
    
    # Create user
    print(f"Creating user: {args.username}")
    user = user_repo.create_user(
        username=args.username,
        password=args.password,
        available_tokens=token_count
    )
    
    if user is None:
        print(f"Error: Username '{args.username}' already exists")
        sys.exit(1)
    
    print("\n" + "="*50)
    print("✓ User created successfully!")
    print("="*50)
    print(f"  User ID:   {user.id}")
    print(f"  Username:  {user.username}")
    print(f"  Tokens:    {user.available_tokens}")
    print(f"  Created:   {user.created_at.isoformat()}")
    print("="*50)
    print("\nYou can now login with:")
    print(f'  curl -X POST "http://localhost:8000/api/v1/auth/login" \\')
    print(f'    -H "Content-Type: application/json" \\')
    print(f'    -d \'{{"username": "{args.username}", "password": "{args.password}"}}\'')
    print()


if __name__ == "__main__":
    main()
