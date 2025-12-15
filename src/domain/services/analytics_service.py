"""
Analytics Service.

High-level service for recording and querying analytics data.
Wraps AnalyticsRepository with business logic and convenience methods.
"""
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List

from src.utils.logger import step_logger


# Global singleton instance
_analytics_service = None


class AnalyticsService:
    """
    Analytics service for tracking system metrics.
    
    Provides high-level methods for:
    - Recording API errors (429, 503, 500)
    - Tracking user sessions
    - Managing daily aggregated metrics
    - Recording LLM provider usage
    """
    
    def __init__(self, repository):
        """
        Initialize analytics service.
        
        Args:
            repository: AnalyticsRepository instance
        """
        self._repo = repository
        step_logger.info("[AnalyticsService] Initialized")
    
    # ============ Error Tracking ============
    
    def record_rate_limit_error(
        self,
        provider: str,
        endpoint: Optional[str] = None,
        user_id: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        """
        Record a 429 rate limit error.
        
        Args:
            provider: Provider that hit rate limit
            endpoint: API endpoint
            user_id: User ID if known
            error_message: Full error message
        """
        if self._repo:
            self._repo.record_error(
                error_code=429,
                provider=provider,
                endpoint=endpoint,
                user_id=user_id,
                error_message=error_message
            )
    
    def record_service_unavailable(
        self,
        provider: str,
        endpoint: Optional[str] = None,
        user_id: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        """
        Record a 503 service unavailable error.
        
        Args:
            provider: Provider that was unavailable
            endpoint: API endpoint
            user_id: User ID if known
            error_message: Full error message
        """
        if self._repo:
            self._repo.record_error(
                error_code=503,
                provider=provider,
                endpoint=endpoint,
                user_id=user_id,
                error_message=error_message
            )
    
    def record_server_error(
        self,
        endpoint: Optional[str] = None,
        user_id: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        """
        Record a 500 internal server error.
        
        Args:
            endpoint: API endpoint
            user_id: User ID if known
            error_message: Full error message
        """
        if self._repo:
            self._repo.record_error(
                error_code=500,
                endpoint=endpoint,
                user_id=user_id,
                error_message=error_message
            )
    
    # ============ Provider Tracking ============
    
    def record_provider_used(
        self,
        provider: str,
        endpoint: Optional[str] = None
    ):
        """
        Record which LLM provider was used for a request.
        
        Args:
            provider: Provider name (main, backup, fallback)
            endpoint: API endpoint
        """
        if self._repo:
            self._repo.record_provider_used(provider, endpoint)
    
    # ============ Session Management ============
    
    def start_or_continue_session(self, user_id: str) -> str:
        """
        Start a new session or continue existing one.
        
        Args:
            user_id: User ID
            
        Returns:
            Session ID
        """
        if not self._repo:
            return ""
        
        # Check for existing active session
        existing = self._repo.get_active_session(user_id)
        if existing:
            return existing["id"]
        
        # Start new session
        return self._repo.start_session(user_id)
    
    def record_message(
        self,
        session_id: str,
        tokens_used: int = 1
    ):
        """
        Record a message in the session.
        
        Args:
            session_id: Session ID
            tokens_used: Tokens consumed by this message
        """
        if self._repo and session_id:
            self._repo.update_session(
                session_id=session_id,
                message_increment=1,
                tokens_increment=tokens_used
            )
    
    def end_session(self, session_id: str):
        """
        End a session.
        
        Args:
            session_id: Session ID
        """
        if self._repo and session_id:
            self._repo.end_session(session_id)
    
    def cleanup_stale_sessions(self, timeout_minutes: int = 30) -> int:
        """
        End sessions that have been inactive.
        
        Args:
            timeout_minutes: Inactivity threshold
            
        Returns:
            Number of sessions ended
        """
        if not self._repo:
            return 0
        return self._repo.end_stale_sessions(timeout_minutes)
    
    # ============ Request Tracking ============
    
    def record_request(
        self,
        endpoint: Optional[str] = None,
        user_id: Optional[str] = None
    ):
        """
        Record an API request.
        
        Args:
            endpoint: API endpoint
            user_id: User ID
        """
        if self._repo:
            self._repo.upsert_daily_metrics(total_requests=1)
            self._repo.update_peak_concurrent()
    
    def record_unique_user(self, user_id: str):
        """
        Record a unique user for today.
        
        Note: This is a simple increment. For true unique counting,
        you'd need to track user IDs in a separate table.
        
        Args:
            user_id: User ID
        """
        # For simplicity, we just track this as part of session start
        pass
    
    # ============ Metrics Retrieval ============
    
    def get_today_summary(self) -> Dict[str, Any]:
        """
        Get today's metrics summary.
        
        Returns:
            Dict with today's metrics
        """
        if not self._repo:
            return {}
        
        metrics = self._repo.get_daily_metrics()
        if not metrics:
            return {
                "date": date.today().isoformat(),
                "total_requests": 0,
                "total_errors": 0,
                "error_429_count": 0,
                "error_503_count": 0,
                "error_500_count": 0,
                "active_sessions": self._repo.get_active_sessions_count()
            }
        
        metrics["active_sessions"] = self._repo.get_active_sessions_count()
        return metrics
    
    def get_error_breakdown(
        self,
        days: int = 7
    ) -> Dict[str, int]:
        """
        Get error counts by type for the last N days.
        
        Args:
            days: Number of days to look back
            
        Returns:
            Dict mapping error type to count
        """
        if not self._repo:
            return {}
        
        start_date = datetime.now() - timedelta(days=days)
        return self._repo.count_events_by_type(start_date=start_date)
    
    def get_recent_events(
        self,
        event_type: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get recent events.
        
        Args:
            event_type: Filter by type (e.g., 'error_429')
            limit: Maximum events to return
            
        Returns:
            List of events
        """
        if not self._repo:
            return []
        
        return self._repo.get_events(event_type=event_type, limit=limit)
    
    def get_metrics_history(
        self,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get daily metrics for the last N days.
        
        Args:
            days: Number of days
            
        Returns:
            List of daily metrics
        """
        if not self._repo:
            return []
        
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        return self._repo.get_metrics_range(start_date, end_date)


def get_analytics_service() -> Optional[AnalyticsService]:
    """
    Get singleton analytics service instance.
    
    Returns:
        AnalyticsService instance or None if not available
    """
    global _analytics_service
    
    if _analytics_service is None:
        from src.infrastructure.database.repository_factory import get_analytics_repository
        repo = get_analytics_repository()
        if repo:
            _analytics_service = AnalyticsService(repo)
    
    return _analytics_service


def reset_analytics_service():
    """Reset singleton for testing."""
    global _analytics_service
    _analytics_service = None
