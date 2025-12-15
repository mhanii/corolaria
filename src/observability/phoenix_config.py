"""
Arize Phoenix Observability Configuration.
Sets up OpenTelemetry tracing for LangGraph workflows and LLM calls.
"""
import os
from typing import Optional
from src.utils.logger import step_logger


# Global tracer provider reference
_tracer_provider = None
_is_initialized = False


def _check_phoenix_available(endpoint: str) -> bool:
    """Check if Phoenix server is reachable."""
    import socket
    from urllib.parse import urlparse
    
    try:
        parsed = urlparse(endpoint)
        host = parsed.hostname or "localhost"
        port = parsed.port or 6006
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def setup_phoenix_tracing(
    phoenix_endpoint: Optional[str] = None,
    project_name: str = "coloraria-rag",
    check_connection: bool = True
) -> bool:
    """
    Set up Arize Phoenix tracing with OpenInference instrumentation.
    
    This instruments:
    - LangChain/LangGraph for workflow tracing
    - Google GenAI (Gemini) for LLM call tracing
    
    Args:
        phoenix_endpoint: Phoenix server endpoint (default: http://localhost:6006)
        project_name: Project name for Phoenix UI
        check_connection: If True, check if Phoenix server is available first
        
    Returns:
        True if tracing was set up successfully
    """
    global _tracer_provider, _is_initialized
    
    if _is_initialized:
        step_logger.info("[Phoenix] Tracing already initialized")
        return True
    
    # Check if Phoenix is disabled via environment variable
    if os.getenv("PHOENIX_ENABLED", "true").lower() == "false":
        step_logger.info("[Phoenix] Tracing disabled via PHOENIX_ENABLED=false")
        return False
    
    # Set Phoenix endpoint - Phoenix expects OTLP traces at /v1/traces
    base_endpoint = phoenix_endpoint or os.getenv("PHOENIX_ENDPOINT", "http://localhost:6006")
    otlp_endpoint = f"{base_endpoint}/v1/traces"
    
    # Check if Phoenix server is available (check base endpoint)
    if check_connection and not _check_phoenix_available(base_endpoint):
        step_logger.warning(f"[Phoenix] Server not available at {base_endpoint} - tracing disabled")
        step_logger.info("[Phoenix] Start Phoenix with: python -m phoenix.server.main serve")
        return False
    
    try:
        # Import Phoenix and OpenInference components
        import phoenix as px
        from phoenix.otel import register
        from openinference.instrumentation.langchain import LangChainInstrumentor
        from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor
        
        step_logger.info(f"[Phoenix] Registering tracer with endpoint: {otlp_endpoint}")
        
        # Register tracer with Phoenix - use OTLP endpoint for traces
        _tracer_provider = register(
            project_name=project_name,
            endpoint=otlp_endpoint
        )
        
        # Instrument LangChain/LangGraph
        LangChainInstrumentor().instrument(tracer_provider=_tracer_provider)
        step_logger.info("[Phoenix] LangChain/LangGraph instrumented")
        
        # Instrument Google GenAI (Gemini)
        GoogleGenAIInstrumentor().instrument(tracer_provider=_tracer_provider)
        step_logger.info("[Phoenix] Google GenAI (Gemini) instrumented")
        
        # Instrument OpenAI / Azure OpenAI
        try:
            from openinference.instrumentation.openai import OpenAIInstrumentor
            OpenAIInstrumentor().instrument(tracer_provider=_tracer_provider)
            step_logger.info("[Phoenix] OpenAI/Azure OpenAI instrumented")
        except ImportError:
            step_logger.debug("[Phoenix] OpenAI instrumentation not available (optional)")
        
        _is_initialized = True
        step_logger.info(f"[Phoenix] ✓ Tracing enabled → {base_endpoint} (project: {project_name})")
        return True
        
    except ImportError as e:
        step_logger.warning(f"[Phoenix] Missing dependencies for tracing: {e}")
        step_logger.info("[Phoenix] Install with: pip install arize-phoenix openinference-instrumentation-langchain openinference-instrumentation-google-genai")
        return False
    except Exception as e:
        step_logger.error(f"[Phoenix] Failed to set up tracing: {e}")
        return False


def shutdown_phoenix_tracing():
    """Shutdown Phoenix tracing gracefully."""
    global _tracer_provider, _is_initialized
    
    if _tracer_provider is not None:
        try:
            _tracer_provider.shutdown()
            step_logger.info("[Phoenix] Tracing shut down successfully")
        except Exception as e:
            step_logger.warning(f"[Phoenix] Error during shutdown: {e}")
        finally:
            _tracer_provider = None
            _is_initialized = False


def is_tracing_enabled() -> bool:
    """Check if Phoenix tracing is currently enabled."""
    return _is_initialized
