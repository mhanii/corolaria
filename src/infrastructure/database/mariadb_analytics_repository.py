"""
MariaDB Analytics Repository.

Handles persistence of analytics events, sessions, and daily metrics.
Uses positional parameters (:p0, :p1, etc.) for SQLAlchemy text() queries.
"""
import json
import uuid
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List

from src.utils.logger import step_logger


class MariaDBAnalyticsRepository:
    """Repository for analytics persistence in MariaDB."""
    
    def __init__(self, connection):
        """
        Initialize repository with database connection.
        
        Args:
            connection: MariaDBConnection instance
        """
        self._connection = connection
    
    # ============ API Events ============
    
    def record_event(
        self,
        event_type: str,
        provider: Optional[str] = None,
        endpoint: Optional[str] = None,
        user_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Record an API event (error, fallback, etc.).
        
        Args:
            event_type: Type of event (e.g., 'error_429', 'error_503', 'fallback')
            provider: LLM provider name (main, backup, fallback)
            endpoint: API endpoint path
            user_id: User ID if authenticated
            details: Additional JSON details
            
        Returns:
            ID of created event record
        """
        query = """
            INSERT INTO api_events (event_type, provider, endpoint, user_id, details, created_at)
            VALUES (:p0, :p1, :p2, :p3, :p4, :p5)
        """
        
        self._connection.execute(query, (
            event_type,
            provider,
            endpoint,
            user_id,
            json.dumps(details) if details else None,
            datetime.now()
        ))
        
        # Get last insert ID
        result = self._connection.fetchone("SELECT LAST_INSERT_ID() as id", ())
        return result["id"] if result else 0
    
    def get_events(
        self,
        event_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Query API events with optional filters."""
        # Build query dynamically based on filters
        if event_type and start_date and end_date:
            query = """
                SELECT id, event_type, provider, endpoint, user_id, details, created_at
                FROM api_events
                WHERE event_type = :p0 AND created_at >= :p1 AND created_at <= :p2
                ORDER BY created_at DESC
                LIMIT :p3
            """
            params = (event_type, start_date, end_date, limit)
        elif event_type and start_date:
            query = """
                SELECT id, event_type, provider, endpoint, user_id, details, created_at
                FROM api_events
                WHERE event_type = :p0 AND created_at >= :p1
                ORDER BY created_at DESC
                LIMIT :p2
            """
            params = (event_type, start_date, limit)
        elif event_type:
            query = """
                SELECT id, event_type, provider, endpoint, user_id, details, created_at
                FROM api_events
                WHERE event_type = :p0
                ORDER BY created_at DESC
                LIMIT :p1
            """
            params = (event_type, limit)
        elif start_date:
            query = """
                SELECT id, event_type, provider, endpoint, user_id, details, created_at
                FROM api_events
                WHERE created_at >= :p0
                ORDER BY created_at DESC
                LIMIT :p1
            """
            params = (start_date, limit)
        else:
            query = """
                SELECT id, event_type, provider, endpoint, user_id, details, created_at
                FROM api_events
                ORDER BY created_at DESC
                LIMIT :p0
            """
            params = (limit,)
        
        results = self._connection.fetchall(query, params)
        
        # Parse JSON details
        for row in results:
            if row.get("details"):
                try:
                    row["details"] = json.loads(row["details"])
                except json.JSONDecodeError:
                    pass
        
        return results
    
    def count_events_by_type(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, int]:
        """Count events grouped by type."""
        if start_date and end_date:
            query = """
                SELECT event_type, COUNT(*) as count
                FROM api_events
                WHERE created_at >= :p0 AND created_at <= :p1
                GROUP BY event_type
            """
            params = (start_date, end_date)
        elif start_date:
            query = """
                SELECT event_type, COUNT(*) as count
                FROM api_events
                WHERE created_at >= :p0
                GROUP BY event_type
            """
            params = (start_date,)
        else:
            query = """
                SELECT event_type, COUNT(*) as count
                FROM api_events
                GROUP BY event_type
            """
            params = ()
        
        results = self._connection.fetchall(query, params)
        return {row["event_type"]: row["count"] for row in results}
    
    # ============ User Sessions ============
    
    def start_session(self, user_id: str) -> str:
        """Start a new user session."""
        session_id = str(uuid.uuid4())
        now = datetime.now()
        
        query = """
            INSERT INTO user_sessions (id, user_id, started_at, last_activity_at, message_count, tokens_consumed)
            VALUES (:p0, :p1, :p2, :p3, 0, 0)
        """
        
        self._connection.execute(query, (session_id, user_id, now, now))
        
        step_logger.info(f"[Analytics] Started session {session_id} for user {user_id}")
        return session_id
    
    def update_session(
        self,
        session_id: str,
        message_increment: int = 0,
        tokens_increment: int = 0
    ) -> bool:
        """Update session activity and stats."""
        query = """
            UPDATE user_sessions
            SET last_activity_at = :p0,
                message_count = message_count + :p1,
                tokens_consumed = tokens_consumed + :p2
            WHERE id = :p3 AND ended_at IS NULL
        """
        
        self._connection.execute(query, (
            datetime.now(),
            message_increment,
            tokens_increment,
            session_id
        ))
        
        return True
    
    def end_session(self, session_id: str) -> bool:
        """End a session."""
        query = """
            UPDATE user_sessions
            SET ended_at = :p0
            WHERE id = :p1 AND ended_at IS NULL
        """
        
        self._connection.execute(query, (datetime.now(), session_id))
        return True
    
    def get_active_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user's active session (last activity within 30 minutes)."""
        threshold = datetime.now() - timedelta(minutes=30)
        
        query = """
            SELECT id, user_id, started_at, last_activity_at, message_count, tokens_consumed
            FROM user_sessions
            WHERE user_id = :p0 
              AND ended_at IS NULL 
              AND last_activity_at > :p1
            ORDER BY last_activity_at DESC
            LIMIT 1
        """
        
        return self._connection.fetchone(query, (user_id, threshold))
    
    def get_active_sessions_count(self, minutes: int = 5) -> int:
        """Count currently active sessions (activity in last N minutes)."""
        threshold = datetime.now() - timedelta(minutes=minutes)
        
        query = """
            SELECT COUNT(DISTINCT user_id) as count
            FROM user_sessions
            WHERE ended_at IS NULL AND last_activity_at > :p0
        """
        
        result = self._connection.fetchone(query, (threshold,))
        return result["count"] if result else 0
    
    def end_stale_sessions(self, timeout_minutes: int = 30) -> int:
        """End sessions that have been inactive for too long."""
        threshold = datetime.now() - timedelta(minutes=timeout_minutes)
        
        # Get count before update
        count_query = """
            SELECT COUNT(*) as count FROM user_sessions
            WHERE ended_at IS NULL AND last_activity_at < :p0
        """
        result = self._connection.fetchone(count_query, (threshold,))
        count = result["count"] if result else 0
        
        if count > 0:
            update_query = """
                UPDATE user_sessions
                SET ended_at = last_activity_at
                WHERE ended_at IS NULL AND last_activity_at < :p0
            """
            self._connection.execute(update_query, (threshold,))
            step_logger.info(f"[Analytics] Ended {count} stale sessions")
        
        return count
    
    # ============ Daily Metrics ============
    
    def upsert_daily_metrics(
        self,
        target_date: Optional[date] = None,
        **increments
    ) -> bool:
        """
        Update or insert daily metrics with increments.
        
        Uses INSERT ... ON DUPLICATE KEY UPDATE for atomic upsert.
        """
        if target_date is None:
            target_date = date.today()
        
        # Valid fields that can be incremented
        valid_fields = {
            'total_requests', 'total_errors', 'error_429_count', 'error_503_count',
            'error_500_count', 'unique_users', 'peak_concurrent_users',
            'avg_session_duration_seconds', 'total_tokens_consumed',
            'provider_main_count', 'provider_backup_count', 'provider_fallback_count'
        }
        
        # Filter to valid fields
        updates = {k: v for k, v in increments.items() if k in valid_fields}
        
        if not updates:
            return False
        
        # For simplicity, handle single field updates
        # Build dynamic query with positional params
        fields = list(updates.keys())
        values = [target_date] + list(updates.values())
        
        # Build insert columns and values
        insert_cols = ["date"] + fields
        insert_placeholders = [f":p{i}" for i in range(len(insert_cols))]
        
        # Build update clause  
        update_parts = []
        for i, field in enumerate(fields):
            # The value is at position i+1 (after date at position 0)
            update_parts.append(f"{field} = {field} + :p{i+1}")
        
        query = f"""
            INSERT INTO daily_metrics ({", ".join(insert_cols)})
            VALUES ({", ".join(insert_placeholders)})
            ON DUPLICATE KEY UPDATE {", ".join(update_parts)}
        """
        
        self._connection.execute(query, tuple(values))
        return True
    
    def update_peak_concurrent(self, target_date: Optional[date] = None) -> int:
        """Update peak concurrent users if current count is higher."""
        if target_date is None:
            target_date = date.today()
        
        current_count = self.get_active_sessions_count()
        
        # Use simple upsert
        query = """
            INSERT INTO daily_metrics (date, peak_concurrent_users)
            VALUES (:p0, :p1)
            ON DUPLICATE KEY UPDATE 
                peak_concurrent_users = GREATEST(peak_concurrent_users, :p1)
        """
        
        self._connection.execute(query, (target_date, current_count))
        return current_count
    
    def get_daily_metrics(self, target_date: Optional[date] = None) -> Optional[Dict[str, Any]]:
        """Get metrics for a specific day."""
        if target_date is None:
            target_date = date.today()
        
        query = """
            SELECT * FROM daily_metrics WHERE date = :p0
        """
        
        return self._connection.fetchone(query, (target_date,))
    
    def get_metrics_range(
        self,
        start_date: date,
        end_date: date
    ) -> List[Dict[str, Any]]:
        """Get metrics for a date range."""
        query = """
            SELECT * FROM daily_metrics
            WHERE date >= :p0 AND date <= :p1
            ORDER BY date DESC
        """
        
        return self._connection.fetchall(query, (start_date, end_date))
    
    # ============ Convenience Methods ============
    
    def record_error(
        self,
        error_code: int,
        provider: Optional[str] = None,
        endpoint: Optional[str] = None,
        user_id: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        """Convenience method to record an error event and update daily metrics."""
        event_type = f"error_{error_code}"
        
        # Record event
        self.record_event(
            event_type=event_type,
            provider=provider,
            endpoint=endpoint,
            user_id=user_id,
            details={"message": error_message} if error_message else None
        )
        
        # Update daily metrics
        increment_field = f"error_{error_code}_count"
        self.upsert_daily_metrics(**{increment_field: 1, "total_errors": 1})
        
        step_logger.info(f"[Analytics] Recorded {event_type} error")
    
    def record_provider_used(self, provider: str, endpoint: Optional[str] = None):
        """Record which provider was used for a request."""
        # Update daily metrics
        field_map = {
            "main": "provider_main_count",
            "backup": "provider_backup_count",
            "fallback": "provider_fallback_count"
        }
        
        field = field_map.get(provider.lower())
        if field:
            self.upsert_daily_metrics(**{field: 1})
        
        # Record event if fallback was used
        if provider.lower() in ("backup", "fallback"):
            self.record_event(
                event_type=f"provider_{provider.lower()}",
                provider=provider,
                endpoint=endpoint
            )
