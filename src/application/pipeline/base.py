"""
Pipeline Base Classes.

Provides Step and Pipeline abstractions for building data processing pipelines
with optional tracing and rollback support.
"""

from time import perf_counter
from typing import Optional, List, Any, TYPE_CHECKING

from src.utils.logger import step_logger

# Conditional imports for tracing
try:
    from opentelemetry.trace import Status, StatusCode
    from src.observability.pipeline_tracing import get_pipeline_tracer
    _TRACING_AVAILABLE = True
except ImportError:
    _TRACING_AVAILABLE = False

if TYPE_CHECKING:
    from src.ingestion.ingestion_context import IngestionContext


class Step:
    """
    Base class for pipeline steps.
    
    Each step processes data and returns the result for the next step.
    Steps should implement the `process` method.
    """
    
    def __init__(self, name: str):
        self.name = name

    def process(self, data: Any) -> Any:
        """
        Process input data and return output.
        
        Args:
            data: Input data from previous step (or initial input)
            
        Returns:
            Processed data for next step
        """
        raise NotImplementedError("Each step must implement the process method.")


class Pipeline:
    """
    Pipeline for sequential data processing with tracing and rollback support.
    
    Features:
    - Sequential execution of steps
    - OpenTelemetry tracing (when enabled)
    - Optional IngestionContext for rollback support
    - Timing and result tracking
    
    Usage:
        steps = [Step1(), Step2(), Step3()]
        pipeline = Pipeline(steps)
        result = pipeline.run(initial_data)
        
        # With tracing context:
        with IngestionContext(law_id, adapter) as ctx:
            pipeline = Pipeline(steps, context=ctx)
            result = pipeline.run(initial_data)
            ctx.commit()  # Mark as successful
    """
    
    def __init__(
        self, 
        steps: List[Step], 
        context: Optional["IngestionContext"] = None,
        pipeline_name: str = "Pipeline"
    ):
        """
        Initialize pipeline.
        
        Args:
            steps: List of Step instances to execute
            context: Optional IngestionContext for rollback support
            pipeline_name: Name for tracing spans
        """
        self.steps = steps
        self.results = {}
        self.context = context
        self.pipeline_name = pipeline_name
        self.step_timings = {}

    def run(self, initial_input: Any = None) -> Any:
        """
        Execute the pipeline.
        
        Runs each step in sequence, with optional tracing and context tracking.
        
        Args:
            initial_input: Initial data for the first step
            
        Returns:
            Output from the final step
            
        Raises:
            Exception: Re-raises any exception from steps after logging
        """
        tracer = get_pipeline_tracer() if _TRACING_AVAILABLE else None
        data = initial_input
        
        # Create parent span for the entire pipeline
        if tracer:
            return self._run_with_tracing(tracer, data)
        else:
            return self._run_without_tracing(data)
    
    def _run_with_tracing(self, tracer, data: Any) -> Any:
        """Execute pipeline with OpenTelemetry tracing."""
        with tracer.start_as_current_span(f"Pipeline.{self.pipeline_name}") as pipeline_span:
            # Set pipeline-level attributes
            pipeline_span.set_attribute("pipeline.name", self.pipeline_name)
            pipeline_span.set_attribute("pipeline.step_count", len(self.steps))
            pipeline_span.set_attribute("pipeline.steps", str([s.name for s in self.steps]))
            
            step_logger.info(f"Pipeline '{self.pipeline_name}' started with {len(self.steps)} steps.")
            pipeline_start = perf_counter()
            
            for step in self.steps:
                with tracer.start_as_current_span(f"Step.{step.name}") as step_span:
                    step_span.set_attribute("step.name", step.name)
                    
                    # Record input info
                    step_span.set_attribute("step.input_type", type(data).__name__)
                    if hasattr(data, "__len__"):
                        try:
                            step_span.set_attribute("step.input_length", len(data))
                        except:
                            pass
                    
                    try:
                        step_start = perf_counter()
                        step_logger.info(f"Step '{step.name}' started.")
                        
                        # Mark step as started in context
                        if self.context:
                            self.context.mark_step_started(step.name)
                        
                        # Execute step
                        data = step.process(data)
                        
                        step_duration = perf_counter() - step_start
                        self.results[step.name] = data
                        self.step_timings[step.name] = step_duration
                        
                        # Record output info
                        step_span.set_attribute("step.output_type", type(data).__name__)
                        step_span.set_attribute("step.duration_seconds", step_duration)
                        if hasattr(data, "__len__"):
                            try:
                                step_span.set_attribute("step.output_length", len(data))
                            except:
                                pass
                        
                        # Record step completion in context
                        if self.context:
                            self.context.record_step(step.name, duration=step_duration)
                        
                        step_span.set_status(Status(StatusCode.OK))
                        step_logger.info(f"Step '{step.name}' finished in {step_duration:.2f}s.")
                        
                    except Exception as e:
                        step_duration = perf_counter() - step_start
                        step_span.set_status(Status(StatusCode.ERROR, str(e)))
                        step_span.record_exception(e)
                        
                        # Mark failure in context
                        if self.context:
                            self.context.mark_failed(step.name, e)
                        
                        step_logger.error(
                            f"Pipeline failed at step '{step.name}' after {step_duration:.2f}s: {str(e)}", 
                            exc_info=True
                        )
                        pipeline_span.set_status(Status(StatusCode.ERROR, f"Failed at {step.name}: {str(e)}"))
                        raise e
            
            pipeline_duration = perf_counter() - pipeline_start
            pipeline_span.set_attribute("pipeline.duration_seconds", pipeline_duration)
            pipeline_span.set_status(Status(StatusCode.OK))
            step_logger.info(f"Pipeline '{self.pipeline_name}' finished in {pipeline_duration:.2f}s.")
            
            return data
    
    def _run_without_tracing(self, data: Any) -> Any:
        """Execute pipeline without tracing."""
        step_logger.info(f"Pipeline '{self.pipeline_name}' started with {len(self.steps)} steps.")
        pipeline_start = perf_counter()
        
        for step in self.steps:
            try:
                step_start = perf_counter()
                step_logger.info(f"Step '{step.name}' started.")
                
                # Mark step as started in context
                if self.context:
                    self.context.mark_step_started(step.name)
                
                # Execute step
                data = step.process(data)
                
                step_duration = perf_counter() - step_start
                self.results[step.name] = data
                self.step_timings[step.name] = step_duration
                
                # Record step completion in context
                if self.context:
                    self.context.record_step(step.name, duration=step_duration)
                
                step_logger.info(f"Step '{step.name}' finished in {step_duration:.2f}s.")
                
            except Exception as e:
                step_duration = perf_counter() - step_start
                
                # Mark failure in context
                if self.context:
                    self.context.mark_failed(step.name, e)
                
                step_logger.error(
                    f"Pipeline failed at step '{step.name}' after {step_duration:.2f}s: {str(e)}", 
                    exc_info=True
                )
                raise e
        
        pipeline_duration = perf_counter() - pipeline_start
        step_logger.info(f"Pipeline '{self.pipeline_name}' finished in {pipeline_duration:.2f}s.")
        
        return data

    def get_result(self, step_name: str) -> Any:
        """Get the result from a specific step."""
        return self.results.get(step_name)
    
    def get_timing(self, step_name: str) -> Optional[float]:
        """Get the execution time for a specific step."""
        return self.step_timings.get(step_name)