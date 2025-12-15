#!/usr/bin/env python3
"""
CLI script to create user accounts.
Used to create tester accounts since registration is disabled.

Usage:
    python scripts/create_user.py <username> <password> [--tokens N]
    
Examples:
    python scripts/create_user.py tester1 securepass123
    python scripts/create_user.py admin adminpass --tokens 5000
    
Note: Uses the configured database (MariaDB by default).
      Set DATABASE_TYPE=sqlite to use SQLite instead.
      
      Environment variables (for MariaDB):
        - MARIADB_URI: Full connection string (preferred)
        - Or individual: MARIADB_HOST, MARIADB_PORT, MARIADB_USER, MARIADB_PASSWORD, MARIADB_DATABASE
"""
import sys
import os
import argparse

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Load .env file for local development
from dotenv import load_dotenv
load_dotenv()


def ensure_mariadb_uri():
    """
    Build MARIADB_URI from individual env vars if not already set.
    This is useful for deployments (like Dokploy) that set individual vars.
    """
    if os.getenv("MARIADB_URI"):
        return  # Already set, nothing to do
    
    # Check if we have the individual components
    host = os.getenv("MARIADB_HOST")
    if not host:
        return  # No host set, let the connection factory handle defaults
    
    port = os.getenv("MARIADB_PORT", "3306")
    user = os.getenv("MARIADB_USER", "coloraria_user")
    password = os.getenv("MARIADB_PASSWORD", "")
    database = os.getenv("MARIADB_DATABASE", "coloraria")
    
    # Build and set the URI
    uri = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
    os.environ["MARIADB_URI"] = uri
    print(f"[create_user] Built MARIADB_URI from env vars (host: {host})")


# Build URI from individual env vars if needed
ensure_mariadb_uri()

# Use the database abstraction layer
from src.infrastructure.database import get_database_connection
from src.infrastructure.database.repository_factory import get_user_repository


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
    
    # Get database connection (uses DATABASE_TYPE env var or config)
    db_type = os.getenv("DATABASE_TYPE", "mariadb")
    print(f"Initializing database ({db_type})...")
    connection = get_database_connection()
    
    # Create repository using the factory
    user_repo = get_user_repository(connection)
    
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
