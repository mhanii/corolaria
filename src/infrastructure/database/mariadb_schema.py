"""
MariaDB schema initialization.
Creates all tables for the application using MariaDB-compatible SQL.
Uses raw pymysql for DDL statements (CREATE TABLE works better without SQLAlchemy text()).
"""
import os
from datetime import datetime
from urllib.parse import urlparse

from src.utils.logger import step_logger


# Current schema version
SCHEMA_VERSION = 5

# Individual table definitions for robust DDL execution
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
    """,
    # ============ Analytics Tables ============
    """
    CREATE TABLE IF NOT EXISTS api_events (
        id INT AUTO_INCREMENT PRIMARY KEY,
        event_type VARCHAR(50) NOT NULL,
        provider VARCHAR(50),
        endpoint VARCHAR(255),
        user_id VARCHAR(36),
        details JSON,
        created_at DATETIME NOT NULL,
        INDEX idx_api_events_type (event_type),
        INDEX idx_api_events_created (created_at),
        INDEX idx_api_events_user (user_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS user_sessions (
        id VARCHAR(36) PRIMARY KEY,
        user_id VARCHAR(36) NOT NULL,
        started_at DATETIME NOT NULL,
        ended_at DATETIME,
        message_count INT DEFAULT 0,
        tokens_consumed INT DEFAULT 0,
        last_activity_at DATETIME NOT NULL,
        INDEX idx_sessions_user (user_id),
        INDEX idx_sessions_started (started_at),
        INDEX idx_sessions_active (last_activity_at),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS daily_metrics (
        id INT AUTO_INCREMENT PRIMARY KEY,
        date DATE NOT NULL UNIQUE,
        total_requests INT DEFAULT 0,
        total_errors INT DEFAULT 0,
        error_429_count INT DEFAULT 0,
        error_503_count INT DEFAULT 0,
        error_500_count INT DEFAULT 0,
        unique_users INT DEFAULT 0,
        peak_concurrent_users INT DEFAULT 0,
        avg_session_duration_seconds INT DEFAULT 0,
        total_tokens_consumed INT DEFAULT 0,
        provider_main_count INT DEFAULT 0,
        provider_backup_count INT DEFAULT 0,
        provider_fallback_count INT DEFAULT 0,
        INDEX idx_daily_date (date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """
]


def init_mariadb_schema(connection) -> bool:
    """
    Initialize MariaDB database schema.
    
    Uses the SQLAlchemy engine's raw connection for DDL (CREATE TABLE) 
    statements which is more reliable than text().
    
    This is called automatically when the MariaDB connection is created.
    
    Args:
        connection: MariaDBConnection instance
        
    Returns:
        True if schema was created, False if it already existed
    """
    step_logger.info("[MariaDB] Checking database schema...")
    
    try:
        # Use SQLAlchemy engine's raw DBAPI connection
        # This ensures we use the same connection parameters
        raw_conn = connection._engine.raw_connection()
        cursor = raw_conn.cursor()
        
        # Check if tables already exist
        cursor.execute("SHOW TABLES LIKE 'users'")
        tables_exist = cursor.fetchone() is not None
        
        if tables_exist:
            step_logger.info("[MariaDB] Schema already exists")
            cursor.close()
            raw_conn.close()
            return False
        
        # Create tables
        step_logger.info("[MariaDB] Creating tables...")
        for table_sql in TABLES:
            cursor.execute(table_sql)
        
        step_logger.info(f"[MariaDB] Created {len(TABLES)} tables")
        
        # Insert schema version
        cursor.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (%s, %s)",
            (SCHEMA_VERSION, datetime.now())
        )
        raw_conn.commit()
        step_logger.info(f"[MariaDB] Schema version {SCHEMA_VERSION} applied")
        
        cursor.close()
        raw_conn.close()
        
        step_logger.info("[MariaDB] Database initialization complete")
        return True
        
    except Exception as e:
        step_logger.error(f"[MariaDB] Schema initialization failed: {e}")
        raise
