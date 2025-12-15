"""
Analytics API v1 endpoints.
Provides endpoints for viewing system metrics and analytics data.
"""
from datetime import date, datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field

from src.api.v1.auth import get_current_user_from_token, TokenPayload
from src.domain.services.analytics_service import get_analytics_service
from src.utils.logger import step_logger


router = APIRouter(prefix="/analytics", tags=["Analytics"])


# ============ Response Schemas ============

class DailyMetricsResponse(BaseModel):
    """Daily metrics summary."""
    date: str = Field(..., description="Date (YYYY-MM-DD)")
    total_requests: int = Field(default=0, description="Total API requests")
    total_errors: int = Field(default=0, description="Total errors")
    error_429_count: int = Field(default=0, description="Rate limit errors")
    error_503_count: int = Field(default=0, description="Service unavailable errors")
    error_500_count: int = Field(default=0, description="Internal server errors")
    unique_users: int = Field(default=0, description="Unique users")
    peak_concurrent_users: int = Field(default=0, description="Peak concurrent sessions")
    total_tokens_consumed: int = Field(default=0, description="Total tokens consumed")
    provider_main_count: int = Field(default=0, description="Main provider usage")
    provider_backup_count: int = Field(default=0, description="Backup provider usage")
    provider_fallback_count: int = Field(default=0, description="Fallback provider usage")
    active_sessions: int = Field(default=0, description="Currently active sessions")


class EventResponse(BaseModel):
    """Single event record."""
    id: int
    event_type: str
    provider: Optional[str] = None
    endpoint: Optional[str] = None
    user_id: Optional[str] = None
    details: Optional[dict] = None
    created_at: str


class EventsListResponse(BaseModel):
    """List of events."""
    events: List[EventResponse]
    total: int


class ErrorBreakdownResponse(BaseModel):
    """Error counts by type."""
    breakdown: dict
    period_days: int


class AnalyticsSummaryResponse(BaseModel):
    """Overall analytics summary."""
    today: DailyMetricsResponse
    last_7_days_errors: dict
    recent_fallbacks: int


# ============ Endpoints ============

@router.get(
    "/summary",
    response_model=AnalyticsSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Analytics Summary",
    description="Get overall analytics summary including today's metrics and recent errors"
)
async def get_summary(
    token: TokenPayload = Depends(get_current_user_from_token)
) -> AnalyticsSummaryResponse:
    """
    Get analytics summary for dashboard.
    
    Returns:
        Summary with today's metrics and error breakdown
    """
    analytics = get_analytics_service()
    
    if not analytics:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Analytics service not available"
        )
    
    # Get today's summary
    today_data = analytics.get_today_summary()
    
    # Convert date to string if needed
    if "date" in today_data and isinstance(today_data["date"], date):
        today_data["date"] = today_data["date"].isoformat()
    elif "date" not in today_data:
        today_data["date"] = date.today().isoformat()
    
    today = DailyMetricsResponse(**today_data)
    
    # Get error breakdown
    error_breakdown = analytics.get_error_breakdown(days=7)
    
    # Count recent fallbacks
    recent_events = analytics.get_recent_events(event_type="provider_fallback", limit=100)
    
    return AnalyticsSummaryResponse(
        today=today,
        last_7_days_errors=error_breakdown,
        recent_fallbacks=len(recent_events)
    )


@router.get(
    "/daily",
    response_model=DailyMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Daily Metrics",
    description="Get metrics for a specific day"
)
async def get_daily_metrics(
    target_date: Optional[str] = Query(None, description="Date (YYYY-MM-DD), defaults to today"),
    token: TokenPayload = Depends(get_current_user_from_token)
) -> DailyMetricsResponse:
    """
    Get metrics for a specific day.
    
    Args:
        target_date: Date string in YYYY-MM-DD format
        
    Returns:
        Daily metrics for the specified date
    """
    analytics = get_analytics_service()
    
    if not analytics:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Analytics service not available"
        )
    
    # Parse date
    if target_date:
        try:
            parsed_date = datetime.strptime(target_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid date format. Use YYYY-MM-DD"
            )
    else:
        parsed_date = date.today()
    
    # Get metrics from repository directly
    from src.infrastructure.database.repository_factory import get_analytics_repository
    repo = get_analytics_repository()
    
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Analytics repository not available"
        )
    
    metrics = repo.get_daily_metrics(parsed_date)
    
    if not metrics:
        # Return empty metrics for that date
        return DailyMetricsResponse(
            date=parsed_date.isoformat(),
            active_sessions=repo.get_active_sessions_count()
        )
    
    # Convert date to string
    if isinstance(metrics.get("date"), date):
        metrics["date"] = metrics["date"].isoformat()
    
    metrics["active_sessions"] = repo.get_active_sessions_count()
    
    return DailyMetricsResponse(**metrics)


@router.get(
    "/events",
    response_model=EventsListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Events",
    description="Query analytics events with optional filters"
)
async def get_events(
    event_type: Optional[str] = Query(None, description="Filter by event type (e.g., error_429)"),
    limit: int = Query(50, ge=1, le=500, description="Maximum events to return"),
    token: TokenPayload = Depends(get_current_user_from_token)
) -> EventsListResponse:
    """
    Query analytics events.
    
    Args:
        event_type: Optional event type filter
        limit: Maximum number of events
        
    Returns:
        List of matching events
    """
    analytics = get_analytics_service()
    
    if not analytics:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Analytics service not available"
        )
    
    events = analytics.get_recent_events(event_type=event_type, limit=limit)
    
    # Convert to response format
    event_responses = []
    for e in events:
        created_at = e.get("created_at")
        if isinstance(created_at, datetime):
            created_at = created_at.isoformat()
        elif created_at is None:
            created_at = ""
        
        event_responses.append(EventResponse(
            id=e.get("id", 0),
            event_type=e.get("event_type", ""),
            provider=e.get("provider"),
            endpoint=e.get("endpoint"),
            user_id=e.get("user_id"),
            details=e.get("details"),
            created_at=created_at
        ))
    
    return EventsListResponse(
        events=event_responses,
        total=len(event_responses)
    )


@router.get(
    "/errors",
    response_model=ErrorBreakdownResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Error Breakdown",
    description="Get error counts grouped by type"
)
async def get_error_breakdown(
    days: int = Query(7, ge=1, le=365, description="Number of days to look back"),
    token: TokenPayload = Depends(get_current_user_from_token)
) -> ErrorBreakdownResponse:
    """
    Get error counts by type.
    
    Args:
        days: Number of days to analyze
        
    Returns:
        Error breakdown by type
    """
    analytics = get_analytics_service()
    
    if not analytics:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Analytics service not available"
        )
    
    breakdown = analytics.get_error_breakdown(days=days)
    
    return ErrorBreakdownResponse(
        breakdown=breakdown,
        period_days=days
    )


@router.get(
    "/history",
    response_model=List[DailyMetricsResponse],
    status_code=status.HTTP_200_OK,
    summary="Get Metrics History",
    description="Get daily metrics for a range of days"
)
async def get_metrics_history(
    days: int = Query(30, ge=1, le=365, description="Number of days of history"),
    token: TokenPayload = Depends(get_current_user_from_token)
) -> List[DailyMetricsResponse]:
    """
    Get historical daily metrics.
    
    Args:
        days: Number of days of history
        
    Returns:
        List of daily metrics
    """
    analytics = get_analytics_service()
    
    if not analytics:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Analytics service not available"
        )
    
    history = analytics.get_metrics_history(days=days)
    
    # Convert to response format
    result = []
    for metrics in history:
        if isinstance(metrics.get("date"), date):
            metrics["date"] = metrics["date"].isoformat()
        metrics["active_sessions"] = 0  # Historical data doesn't have live sessions
        result.append(DailyMetricsResponse(**metrics))
    
    return result
