"""
Benchmark Tracing for Phoenix Observability.

Provides utilities for tracing benchmark runs with proper tagging
and flagging of incorrect answers for Phoenix visualization.
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
    step_logger.debug("[BenchmarkTracing] OpenTelemetry not available - tracing disabled")


# Global tracer for benchmarks
_benchmark_tracer = None


def get_benchmark_tracer():
    """Get the OpenTelemetry tracer for benchmarks."""
    global _benchmark_tracer
    
    if not _OTEL_AVAILABLE:
        return None
    
    if _benchmark_tracer is None:
        _benchmark_tracer = trace.get_tracer("benchmark")
    
    return _benchmark_tracer


@contextmanager
def trace_question(
    question_id: int,
    question_text: str = "",
):
    """
    Context manager for tracing a single benchmark question.
    
    Usage:
        with trace_question(question_id=1, question_text="...") as span:
            # ... run question
            span.set_result(model_answer="a", correct_answer="b", is_correct=False)
    
    Args:
        question_id: The question number/ID
        question_text: Optional question text for context
    
    Yields:
        QuestionSpanWrapper that allows setting results
    """
    tracer = get_benchmark_tracer()
    
    if tracer is None:
        # No tracing, yield a no-op wrapper
        yield _NoOpSpanWrapper()
        return
    
    with tracer.start_as_current_span(f"BenchmarkQuestion.{question_id}") as span:
        span.set_attribute("benchmark.mode", True)
        span.set_attribute("benchmark.question_id", question_id)
        if question_text:
            # Truncate long questions for attributes
            span.set_attribute("benchmark.question_text", question_text[:500])
        
        wrapper = _QuestionSpanWrapper(span)
        try:
            yield wrapper
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise


class _NoOpSpanWrapper:
    """No-op wrapper when tracing is disabled."""
    
    def set_result(
        self,
        model_answer: Optional[str],
        correct_answer: Optional[str],
        is_correct: Optional[bool],
        raw_response: str = ""
    ):
        pass


class _QuestionSpanWrapper:
    """Wrapper for question spans to set results."""
    
    def __init__(self, span: "Span"):
        self._span = span
    
    def set_result(
        self,
        model_answer: Optional[str],
        correct_answer: Optional[str],
        is_correct: Optional[bool],
        raw_response: str = ""
    ):
        """
        Set the result of the question.
        
        Args:
            model_answer: The answer extracted from the model response
            correct_answer: The expected correct answer
            is_correct: Whether the model answered correctly
            raw_response: The raw model response text
        """
        self._span.set_attribute("benchmark.model_answer", model_answer or "")
        self._span.set_attribute("benchmark.correct_answer", correct_answer or "")
        
        if raw_response:
            # Truncate long responses
            self._span.set_attribute("benchmark.raw_response", raw_response[:1000])
        
        if is_correct is None:
            self._span.set_attribute("benchmark.is_correct", "unknown")
            self._span.set_status(Status(StatusCode.UNSET))
        elif is_correct:
            self._span.set_attribute("benchmark.is_correct", True)
            self._span.set_status(Status(StatusCode.OK))
        else:
            # Flag incorrect answers with ERROR status
            self._span.set_attribute("benchmark.is_correct", False)
            self._span.set_status(Status(
                StatusCode.ERROR,
                f"Incorrect: model={model_answer}, expected={correct_answer}"
            ))


class BenchmarkSessionTracer:
    """
    Context manager for tracing an entire benchmark session/exam.
    
    Usage:
        with BenchmarkSessionTracer(
            exam_name="OposicionesExam",
            model_name="gemini-2.5-flash",
            use_rag=True
        ) as session:
            # ... run all questions
            session.set_final_results(correct=8, incorrect=2, total=10)
    """
    
    def __init__(
        self,
        exam_name: str,
        model_name: str,
        use_rag: bool,
        parameters: Optional[Dict[str, Any]] = None
    ):
        self.exam_name = exam_name
        self.model_name = model_name
        self.use_rag = use_rag
        self.parameters = parameters or {}
        self.tracer = get_benchmark_tracer()
        self._span = None
        self._span_context = None
    
    def __enter__(self) -> "BenchmarkSessionTracer":
        if self.tracer is None:
            return self
        
        self._span_context = self.tracer.start_as_current_span("BenchmarkSession")
        self._span = self._span_context.__enter__()
        
        # Tag with benchmark mode
        self._span.set_attribute("benchmark.mode", True)
        self._span.set_attribute("benchmark.exam_name", self.exam_name)
        self._span.set_attribute("benchmark.model_name", self.model_name)
        self._span.set_attribute("benchmark.use_rag", self.use_rag)
        
        # Log parameters
        for key, value in self.parameters.items():
            if value is not None:
                self._span.set_attribute(f"benchmark.param.{key}", str(value))
        
        step_logger.info(f"[BenchmarkTracing] Started session: {self.exam_name} (model={self.model_name})")
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
    
    def set_final_results(
        self,
        correct: int,
        incorrect: int,
        unanswered: int,
        total: int,
        score_percent: float,
        execution_time_ms: float
    ):
        """Set the final results of the benchmark session."""
        if self._span is None:
            return
        
        self._span.set_attribute("benchmark.result.correct", correct)
        self._span.set_attribute("benchmark.result.incorrect", incorrect)
        self._span.set_attribute("benchmark.result.unanswered", unanswered)
        self._span.set_attribute("benchmark.result.total", total)
        self._span.set_attribute("benchmark.result.score_percent", score_percent)
        self._span.set_attribute("benchmark.result.execution_time_ms", execution_time_ms)
        
        step_logger.info(
            f"[BenchmarkTracing] Session complete: {correct}/{total} "
            f"({score_percent:.1f}%) in {execution_time_ms/1000:.1f}s"
        )
    
    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        """Add an event to the session span."""
        if self._span:
            self._span.add_event(name, attributes or {})
