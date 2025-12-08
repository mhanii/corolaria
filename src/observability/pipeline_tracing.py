"""
Pipeline Tracing with OpenTelemetry.

Provides tracing utilities for the ingestion pipeline, integrated with Phoenix
for visualization. Uses OpenTelemetry API which Phoenix supports via OTLP.
"""

from functools import wraps
from typing import Any, Callable, Optional
from src.utils.logger import step_logger

# OpenTelemetry imports - graceful fallback if not installed
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode, Span
    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False
    step_logger.warning("[PipelineTracing] OpenTelemetry not available - tracing disabled")


# Global tracer instance for the ingestion pipeline
_tracer = None


def get_pipeline_tracer():
    """
    Get the OpenTelemetry tracer for the ingestion pipeline.
    
    Returns a tracer named "ingestion_pipeline" that will be captured
    by Phoenix when tracing is enabled.
    
    Returns:
        Tracer instance or None if OpenTelemetry is not available
    """
    global _tracer
    
    if not _OTEL_AVAILABLE:
        return None
    
    if _tracer is None:
        _tracer = trace.get_tracer("ingestion_pipeline")
    
    return _tracer


def trace_step(step_name: str):
    """
    Decorator to trace a pipeline step.
    
    Creates a span for the decorated function, recording:
    - Step name
    - Input/output types
    - Execution status (OK/ERROR)
    - Exceptions if any
    
    Usage:
        class MyStep(Step):
            @trace_step("my_step")
            def process(self, data):
                # ... processing logic
                return result
    
    Args:
        step_name: Name of the step for the span
        
    Returns:
        Decorated function with tracing
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, data, *args, **kwargs):
            tracer = get_pipeline_tracer()
            
            if tracer is None:
                # Tracing not available, just run the function
                return func(self, data, *args, **kwargs)
            
            with tracer.start_as_current_span(f"Step.{step_name}") as span:
                # Record input information
                span.set_attribute("step.name", step_name)
                span.set_attribute("step.input_type", type(data).__name__)
                
                # Add input summary if available
                if hasattr(data, "__len__"):
                    try:
                        span.set_attribute("step.input_length", len(data))
                    except:
                        pass
                
                try:
                    result = func(self, data, *args, **kwargs)
                    
                    # Record output information
                    span.set_attribute("step.output_type", type(result).__name__)
                    if hasattr(result, "__len__"):
                        try:
                            span.set_attribute("step.output_length", len(result))
                        except:
                            pass
                    
                    span.set_status(Status(StatusCode.OK))
                    return result
                    
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise
        
        return wrapper
    return decorator


class PipelineTracer:
    """
    Context manager for tracing an entire pipeline run.
    
    Creates a parent span for the pipeline and provides methods
    to create child spans for individual steps.
    
    Usage:
        with PipelineTracer("Doc2Graph", law_id="BOE-A-1978-31229") as tracer:
            with tracer.step_span("data_retriever"):
                # ... step logic
            with tracer.step_span("data_processor"):
                # ... step logic
    """
    
    def __init__(self, pipeline_name: str, **attributes):
        """
        Initialize pipeline tracer.
        
        Args:
            pipeline_name: Name of the pipeline for the parent span
            **attributes: Additional attributes to add to the pipeline span
        """
        self.pipeline_name = pipeline_name
        self.attributes = attributes
        self.tracer = get_pipeline_tracer()
        self._pipeline_span: Optional[Span] = None
        self._span_context = None
    
    def __enter__(self) -> "PipelineTracer":
        """Enter the pipeline span context."""
        if self.tracer is None:
            return self
        
        self._span_context = self.tracer.start_as_current_span(
            f"Pipeline.{self.pipeline_name}"
        )
        self._pipeline_span = self._span_context.__enter__()
        
        # Set pipeline attributes
        for key, value in self.attributes.items():
            if value is not None:
                self._pipeline_span.set_attribute(f"pipeline.{key}", str(value))
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the pipeline span context."""
        if self._span_context is None:
            return False
        
        if exc_type is not None and self._pipeline_span:
            self._pipeline_span.set_status(Status(StatusCode.ERROR, str(exc_val)))
            self._pipeline_span.record_exception(exc_val)
        elif self._pipeline_span:
            self._pipeline_span.set_status(Status(StatusCode.OK))
        
        return self._span_context.__exit__(exc_type, exc_val, exc_tb)
    
    def step_span(self, step_name: str, **attributes):
        """
        Create a span for a pipeline step.
        
        Args:
            step_name: Name of the step
            **attributes: Additional attributes for the span
            
        Returns:
            Context manager for the step span
        """
        if self.tracer is None:
            return _NoOpContextManager()
        
        span = self.tracer.start_as_current_span(f"Step.{step_name}")
        # Note: attributes will be set when the span is active
        return _StepSpanContext(span, step_name, attributes)
    
    def set_attribute(self, key: str, value: Any) -> None:
        """Set an attribute on the pipeline span."""
        if self._pipeline_span:
            self._pipeline_span.set_attribute(key, str(value))
    
    def add_event(self, name: str, attributes: Optional[dict] = None) -> None:
        """Add an event to the pipeline span."""
        if self._pipeline_span:
            self._pipeline_span.add_event(name, attributes or {})


class _StepSpanContext:
    """Context manager wrapper for step spans with automatic attribute setting."""
    
    def __init__(self, span_context, step_name: str, attributes: dict):
        self._span_context = span_context
        self.step_name = step_name
        self.attributes = attributes
        self._span = None
    
    def __enter__(self):
        self._span = self._span_context.__enter__()
        self._span.set_attribute("step.name", self.step_name)
        for key, value in self.attributes.items():
            if value is not None:
                self._span.set_attribute(f"step.{key}", str(value))
        return self._span
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self._span.set_status(Status(StatusCode.ERROR, str(exc_val)))
            self._span.record_exception(exc_val)
        else:
            self._span.set_status(Status(StatusCode.OK))
        return self._span_context.__exit__(exc_type, exc_val, exc_tb)


class _NoOpContextManager:
    """No-op context manager for when tracing is disabled."""
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        return False
    
    def set_attribute(self, *args):
        pass
    
    def set_status(self, *args):
        pass
    
    def record_exception(self, *args):
        pass
    
    def add_event(self, *args):
        pass
