"""
Beta Testing Tracing for Phoenix Observability.

Provides utilities for tagging spans with test mode attributes
and feedback annotations for Phoenix.
"""
from contextlib import contextmanager
from typing import Optional, Dict, Any
from src.utils.logger import step_logger

# OpenTelemetry imports - graceful fallback if not installed
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode, Span
    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False
    step_logger.debug("[BetaTracing] OpenTelemetry not available - tracing disabled")


# Global tracer for beta testing
_beta_tracer = None


def get_beta_tracer():
    """Get the OpenTelemetry tracer for beta testing."""
    global _beta_tracer
    
    if not _OTEL_AVAILABLE:
        return None
    
    if _beta_tracer is None:
        _beta_tracer = trace.get_tracer("beta_testing")
    
    return _beta_tracer


def tag_current_span_as_test_mode(
    user_id: str,
    is_test_user: bool = True,
    config_matrix: Optional[Dict[str, Any]] = None
) -> None:
    """
    Tag the current span with test mode attributes.
    
    This should be called early in a request to mark it as a test session.
    
    Args:
        user_id: User ID for the test session
        is_test_user: Whether this is a test user
        config_matrix: Config matrix used for the response
    """
    if not _OTEL_AVAILABLE:
        return
    
    try:
        span = trace.get_current_span()
        if span and span.is_recording():
            span.set_attribute("beta.test_mode", True)
            span.set_attribute("beta.user_id", user_id)
            span.set_attribute("beta.is_test_user", is_test_user)
            
            if config_matrix:
                for key, value in config_matrix.items():
                    if value is not None:
                        span.set_attribute(f"beta.config.{key}", str(value))
            
            step_logger.debug(f"[BetaTracing] Tagged span as test mode (user={user_id})")
    except Exception as e:
        step_logger.warning(f"[BetaTracing] Failed to tag span: {e}")


def annotate_response_feedback(
    conversation_id: str,
    message_id: int,
    feedback_type: str,
    config_matrix: Optional[Dict[str, Any]] = None
) -> None:
    """
    Annotate a span with feedback information.
    
    This can be used to correlate feedback with specific responses.
    
    Args:
        conversation_id: ID of the conversation
        message_id: ID of the message
        feedback_type: Type of feedback (like, dislike, report)
        config_matrix: Config matrix used for the response
    """
    tracer = get_beta_tracer()
    
    if tracer is None:
        return
    
    with tracer.start_as_current_span("FeedbackAnnotation") as span:
        span.set_attribute("feedback.conversation_id", conversation_id)
        span.set_attribute("feedback.message_id", message_id)
        span.set_attribute("feedback.type", feedback_type)
        
        if config_matrix:
            span.set_attribute("feedback.config.model", config_matrix.get("model", "unknown"))
            span.set_attribute("feedback.config.top_k", config_matrix.get("top_k", 0))
            span.set_attribute("feedback.config.collector", config_matrix.get("collector_type", "unknown"))
        
        step_logger.info(f"[BetaTracing] Annotated feedback: {feedback_type} for msg {message_id}")


class BetaSessionTracer:
    """
    Context manager for tracing an entire beta testing session.
    
    Usage:
        with BetaSessionTracer(user_id="123", is_test_user=True) as tracer:
            # ... handle request
            tracer.set_config_matrix(config)
    """
    
    def __init__(self, user_id: str, is_test_user: bool = True):
        self.user_id = user_id
        self.is_test_user = is_test_user
        self.tracer = get_beta_tracer()
        self._span = None
        self._span_context = None
    
    def __enter__(self) -> "BetaSessionTracer":
        if self.tracer is None:
            return self
        
        self._span_context = self.tracer.start_as_current_span("BetaSession")
        self._span = self._span_context.__enter__()
        
        self._span.set_attribute("beta.user_id", self.user_id)
        self._span.set_attribute("beta.is_test_user", self.is_test_user)
        self._span.set_attribute("beta.test_mode", True)
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._span_context is None:
            return False
        
        if exc_type is not None and self._span:
            self._span.set_status(Status(StatusCode.ERROR, str(exc_val)))
            self._span.record_exception(exc_val)
        elif self._span:
            self._span.set_status(Status(StatusCode.OK))
        
        return self._span_context.__exit__(exc_type, exc_val, exc_tb)
    
    def set_config_matrix(self, config_matrix: Dict[str, Any]):
        """Set the config matrix used for this session."""
        if self._span and config_matrix:
            for key, value in config_matrix.items():
                if value is not None:
                    self._span.set_attribute(f"beta.config.{key}", str(value))
    
    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        """Add an event to the session span."""
        if self._span:
            self._span.add_event(name, attributes or {})
