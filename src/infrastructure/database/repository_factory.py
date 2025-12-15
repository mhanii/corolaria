"""
Repository factory module.
Creates appropriate repository instances based on database configuration.
"""
import os
from typing import Optional

from src.infrastructure.database.connection_factory import get_database_connection
from src.utils.logger import step_logger


def get_user_repository(connection=None):
    """
    Get user repository for the configured database type.
    
    Args:
        connection: Optional database connection (will create if not provided)
        
    Returns:
        UserRepository instance (SQLite or MariaDB)
    """
    db_type = os.getenv("DATABASE_TYPE", "mariadb")
    
    if connection is None:
        connection = get_database_connection()
    
    if db_type == "mariadb":
        from src.infrastructure.database.mariadb_user_repository import MariaDBUserRepository
        return MariaDBUserRepository(connection)
    else:
        from src.infrastructure.sqlite.user_repository import UserRepository
        # Legacy SQLite uses the underlying connection
        if hasattr(connection, 'legacy_connection'):
            return UserRepository(connection.legacy_connection)
        return UserRepository(connection)


def get_conversation_repository(connection=None):
    """
    Get conversation repository for the configured database type.
    
    Args:
        connection: Optional database connection (will create if not provided)
        
    Returns:
        ConversationRepository instance (SQLite or MariaDB)
    """
    db_type = os.getenv("DATABASE_TYPE", "mariadb")
    
    if connection is None:
        connection = get_database_connection()
    
    if db_type == "mariadb":
        from src.infrastructure.database.mariadb_conversation_repository import MariaDBConversationRepository
        return MariaDBConversationRepository(connection)
    else:
        from src.infrastructure.sqlite.conversation_repository import ConversationRepository
        if hasattr(connection, 'legacy_connection'):
            return ConversationRepository(connection.legacy_connection)
        return ConversationRepository(connection)


def get_feedback_repository(connection=None):
    """Get feedback repository for the configured database type."""
    db_type = os.getenv("DATABASE_TYPE", "mariadb")
    
    if connection is None:
        connection = get_database_connection()
    
    if db_type == "mariadb":
        from src.infrastructure.database.mariadb_beta_repository import MariaDBFeedbackRepository
        return MariaDBFeedbackRepository(connection)
    else:
        from src.infrastructure.sqlite.beta_repository import FeedbackRepository
        if hasattr(connection, 'legacy_connection'):
            return FeedbackRepository(connection.legacy_connection)
        return FeedbackRepository(connection)


def get_survey_repository(connection=None):
    """Get survey repository for the configured database type."""
    db_type = os.getenv("DATABASE_TYPE", "mariadb")
    
    if connection is None:
        connection = get_database_connection()
    
    if db_type == "mariadb":
        from src.infrastructure.database.mariadb_beta_repository import MariaDBSurveyRepository
        return MariaDBSurveyRepository(connection)
    else:
        from src.infrastructure.sqlite.beta_repository import SurveyRepository
        if hasattr(connection, 'legacy_connection'):
            return SurveyRepository(connection.legacy_connection)
        return SurveyRepository(connection)


def get_all_repositories(connection=None):
    """
    Get all repositories as a dict.
    
    Returns:
        Dict with keys: user, conversation, feedback, survey, analytics
    """
    if connection is None:
        connection = get_database_connection()
    
    return {
        "user": get_user_repository(connection),
        "conversation": get_conversation_repository(connection),
        "feedback": get_feedback_repository(connection),
        "survey": get_survey_repository(connection),
        "analytics": get_analytics_repository(connection)
    }


def get_analytics_repository(connection=None):
    """
    Get analytics repository for the configured database type.
    
    Note: Analytics is only available for MariaDB. Returns None for SQLite.
    
    Args:
        connection: Optional database connection (will create if not provided)
        
    Returns:
        AnalyticsRepository instance (MariaDB only) or None
    """
    db_type = os.getenv("DATABASE_TYPE", "mariadb")
    
    if connection is None:
        connection = get_database_connection()
    
    if db_type == "mariadb":
        from src.infrastructure.database.mariadb_analytics_repository import MariaDBAnalyticsRepository
        return MariaDBAnalyticsRepository(connection)
    else:
        step_logger.warning("[RepositoryFactory] Analytics not available for SQLite")
        return None
