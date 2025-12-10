"""
SQLite database schema initialization.
Creates tables for users, conversations, messages, and citations.
"""
from src.infrastructure.sqlite.connection import SQLiteConnection
from src.utils.logger import step_logger


# Database schema version for migrations
SCHEMA_VERSION = 4

# SQL statements for table creation
SCHEMA_SQL = """
-- Users table
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    available_tokens INTEGER DEFAULT 1000,
    created_at TEXT NOT NULL,
    is_active INTEGER DEFAULT 1
);

-- Conversations table
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Messages table
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    metadata TEXT,
    context_json TEXT,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

-- Message citations table (for assistant messages)
CREATE TABLE IF NOT EXISTS message_citations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL,
    citation_index INTEGER NOT NULL,
    cite_key TEXT NOT NULL,
    display_text TEXT,
    article_id TEXT NOT NULL,
    article_number TEXT NOT NULL,
    article_text TEXT,
    normativa_title TEXT NOT NULL,
    article_path TEXT,
    score REAL DEFAULT 0.0,
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- Beta testing tables (v4)
CREATE TABLE IF NOT EXISTS feedback (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    message_id INTEGER NOT NULL,
    conversation_id TEXT NOT NULL,
    feedback_type TEXT NOT NULL,
    comment TEXT,
    config_matrix TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (message_id) REFERENCES messages(id)
);

CREATE TABLE IF NOT EXISTS surveys (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    responses TEXT NOT NULL,
    tokens_granted INTEGER NOT NULL,
    submitted_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS arena_comparisons (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    query TEXT NOT NULL,
    response_a TEXT NOT NULL,
    response_b TEXT NOT NULL,
    config_a TEXT NOT NULL,
    config_b TEXT NOT NULL,
    citations_a TEXT,
    citations_b TEXT,
    context_a TEXT,
    context_b TEXT,
    user_preference TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_message_citations_message_id ON message_citations(message_id);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_feedback_user_id ON feedback(user_id);
CREATE INDEX IF NOT EXISTS idx_feedback_message_id ON feedback(message_id);
CREATE INDEX IF NOT EXISTS idx_surveys_user_id ON surveys(user_id);
CREATE INDEX IF NOT EXISTS idx_arena_user_id ON arena_comparisons(user_id);
"""

# Migrations dictionary: version -> SQL to upgrade from previous version
MIGRATIONS = {
    2: """
    -- Add context_json column to messages table for storing context used in responses
    ALTER TABLE messages ADD COLUMN context_json TEXT;
    """,
    3: """
    -- Add cite_key and display_text columns for semantic citation system
    ALTER TABLE message_citations ADD COLUMN cite_key TEXT;
    ALTER TABLE message_citations ADD COLUMN display_text TEXT;
    """,
    4: """
    -- Beta testing tables
    
    -- Feedback table for like/dislike/report
    CREATE TABLE IF NOT EXISTS feedback (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        message_id INTEGER NOT NULL,
        conversation_id TEXT NOT NULL,
        feedback_type TEXT NOT NULL,
        comment TEXT,
        config_matrix TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (message_id) REFERENCES messages(id)
    );
    
    -- Surveys table for token refill
    CREATE TABLE IF NOT EXISTS surveys (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        responses TEXT NOT NULL,
        tokens_granted INTEGER NOT NULL,
        submitted_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    
    -- Arena comparisons table for A/B testing
    CREATE TABLE IF NOT EXISTS arena_comparisons (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        query TEXT NOT NULL,
        response_a TEXT NOT NULL,
        response_b TEXT NOT NULL,
        config_a TEXT NOT NULL,
        config_b TEXT NOT NULL,
        citations_a TEXT,
        citations_b TEXT,
        user_preference TEXT,
        created_at TEXT NOT NULL,
        resolved_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    
    -- Indexes for beta testing tables
    CREATE INDEX IF NOT EXISTS idx_feedback_user_id ON feedback(user_id);
    CREATE INDEX IF NOT EXISTS idx_feedback_message_id ON feedback(message_id);
    CREATE INDEX IF NOT EXISTS idx_surveys_user_id ON surveys(user_id);
    CREATE INDEX IF NOT EXISTS idx_arena_user_id ON arena_comparisons(user_id);
    """
}


def _run_migrations(connection, current_version: int, target_version: int):
    """Run migrations from current_version to target_version."""
    from datetime import datetime
    
    for version in range(current_version + 1, target_version + 1):
        if version in MIGRATIONS:
            step_logger.info(f"[SQLite] Running migration to version {version}...")
            try:
                connection.executescript(MIGRATIONS[version])
                connection.execute(
                    "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                    (version, datetime.now().isoformat())
                )
                connection.commit()
                step_logger.info(f"[SQLite] Migration to version {version} complete")
            except Exception as e:
                # Column might already exist if we're re-running
                if "duplicate column" in str(e).lower():
                    step_logger.info(f"[SQLite] Migration {version}: column already exists, skipping")
                    connection.execute(
                        "INSERT OR REPLACE INTO schema_version (version, applied_at) VALUES (?, ?)",
                        (version, datetime.now().isoformat())
                    )
                    connection.commit()
                else:
                    raise


def init_database(db_path: str = "data/coloraria.db") -> SQLiteConnection:
    """
    Initialize the database with schema.
    
    Creates all tables if they don't exist and returns connection manager.
    
    Args:
        db_path: Path to SQLite database file
        
    Returns:
        SQLiteConnection instance
    """
    conn_manager = SQLiteConnection.get_instance(db_path)
    connection = conn_manager.get_connection()
    
    step_logger.info("[SQLite] Initializing database schema...")
    
    # Execute schema creation
    connection.executescript(SCHEMA_SQL)
    
    # Check/set schema version
    cursor = connection.cursor()
    cursor.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
    row = cursor.fetchone()
    
    if row is None:
        # First time - insert schema version
        from datetime import datetime
        cursor.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, datetime.now().isoformat())
        )
        connection.commit()
        step_logger.info(f"[SQLite] Schema version {SCHEMA_VERSION} applied")
    else:
        current_version = row[0]
        step_logger.info(f"[SQLite] Database schema version: {current_version}")
        
        # Run migrations if needed
        if current_version < SCHEMA_VERSION:
            _run_migrations(connection, current_version, SCHEMA_VERSION)
    
    step_logger.info("[SQLite] Database initialization complete")
    return conn_manager

