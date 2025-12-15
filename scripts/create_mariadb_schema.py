#!/usr/bin/env python3
"""
Simple script to create MariaDB schema directly.
Run this first before migration.

Usage:
    python scripts/create_mariadb_schema.py
"""
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# MariaDB schema - each CREATE TABLE as a separate statement
TABLES = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id VARCHAR(36) PRIMARY KEY,
        username VARCHAR(255) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        available_tokens INT DEFAULT 1000,
        created_at DATETIME NOT NULL,
        is_active TINYINT(1) DEFAULT 1,
        INDEX idx_users_username (username)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS conversations (
        id VARCHAR(36) PRIMARY KEY,
        user_id VARCHAR(36) NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        metadata JSON,
        INDEX idx_conversations_user_id (user_id),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS messages (
        id INT AUTO_INCREMENT PRIMARY KEY,
        conversation_id VARCHAR(36) NOT NULL,
        role VARCHAR(50) NOT NULL,
        content LONGTEXT NOT NULL,
        timestamp DATETIME NOT NULL,
        metadata JSON,
        context_json LONGTEXT,
        INDEX idx_messages_conversation_id (conversation_id),
        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS message_citations (
        id INT AUTO_INCREMENT PRIMARY KEY,
        message_id INT NOT NULL,
        citation_index INT NOT NULL,
        cite_key VARCHAR(255),
        display_text TEXT,
        article_id VARCHAR(255) NOT NULL,
        article_number VARCHAR(255) NOT NULL,
        article_text LONGTEXT,
        normativa_title VARCHAR(500) NOT NULL,
        article_path TEXT,
        score FLOAT DEFAULT 0.0,
        INDEX idx_message_citations_message_id (message_id),
        FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS schema_version (
        version INT PRIMARY KEY,
        applied_at DATETIME NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS feedback (
        id VARCHAR(36) PRIMARY KEY,
        user_id VARCHAR(36) NOT NULL,
        message_id INT NOT NULL,
        conversation_id VARCHAR(36) NOT NULL,
        feedback_type VARCHAR(50) NOT NULL,
        comment TEXT,
        config_matrix JSON NOT NULL,
        created_at DATETIME NOT NULL,
        INDEX idx_feedback_user_id (user_id),
        INDEX idx_feedback_message_id (message_id),
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (message_id) REFERENCES messages(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS surveys (
        id VARCHAR(36) PRIMARY KEY,
        user_id VARCHAR(36) NOT NULL,
        responses JSON NOT NULL,
        tokens_granted INT NOT NULL,
        submitted_at DATETIME NOT NULL,
        INDEX idx_surveys_user_id (user_id),
        FOREIGN KEY (user_id) REFERENCES users(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """
]


def main():
    import pymysql
    
    print("=" * 60)
    print("MariaDB Schema Creation")
    print("=" * 60)
    
    # Get connection parameters
    host = os.getenv("MARIADB_HOST", "localhost")
    port = int(os.getenv("MARIADB_PORT", "3306"))
    db = os.getenv("MARIADB_DATABASE", "coloraria")
    user = os.getenv("MARIADB_USER", "coloraria_user")
    password = os.getenv("MARIADB_PASSWORD", "coloraria_pass")
    
    print(f"\nConnecting to {host}:{port}/{db} as {user}...")
    
    try:
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=db,
            autocommit=True
        )
        print("✓ Connected to MariaDB")
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        sys.exit(1)
    
    print("\nCreating tables...")
    cursor = conn.cursor()
    
    for i, table_sql in enumerate(TABLES):
        try:
            cursor.execute(table_sql)
            # Extract table name from SQL
            table_name = table_sql.split("CREATE TABLE IF NOT EXISTS")[1].split("(")[0].strip()
            print(f"  ✓ {table_name}")
        except Exception as e:
            print(f"  ✗ Table {i+1} failed: {e}")
    
    # Verify tables exist
    print("\nVerifying tables...")
    cursor.execute("SHOW TABLES")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"  Found {len(tables)} tables: {', '.join(tables)}")
    
    cursor.close()
    conn.close()
    
    print("\n✓ Schema creation complete!")


if __name__ == "__main__":
    main()
