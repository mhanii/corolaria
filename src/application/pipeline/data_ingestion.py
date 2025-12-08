from .base import Step
from src.infrastructure.http.http_client import BOEHTTPClient
import asyncio
import concurrent.futures

# Import tracing (optional)
try:
    from opentelemetry import trace
    _tracer = trace.get_tracer("data_retriever")
except ImportError:
    _tracer = None


class DataRetriever(Step):
    def __init__(self, name: str, search_criteria: str = "default"):
        super().__init__(name)
        self.search_criteria = search_criteria
        self.client = BOEHTTPClient()
        
    def _run_coro_sync(self, coro):
        """
        Run coroutine from synchronous code.
        Uses asyncio.run when no running loop; otherwise runs the coroutine in a new loop on a thread.
        """
        try:
            # If there's no running loop, this will succeed and block until complete.
            return asyncio.run(coro)
        except RuntimeError:
            # There's a running event loop (e.g., in tests or notebooks) — run in a separate thread.
            def _run_in_new_loop(c):
                loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(loop)
                    return loop.run_until_complete(c)
                finally:
                    loop.close()

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(_run_in_new_loop, coro)
                return future.result()

    def process(self, data):
        """Retrieve law data from BOE API."""
        # Add tracing attributes
        if _tracer:
            current_span = trace.get_current_span()
            if current_span and current_span.is_recording():
                current_span.set_attribute("retriever.law_id", self.search_criteria)
                current_span.set_attribute("retriever.source", "BOE API")
        
        # Fetch the data
        result = self._run_coro_sync(self.client.get_law_by_id(self.search_criteria))
        
        # Add output attributes
        if _tracer:
            current_span = trace.get_current_span()
            if current_span and current_span.is_recording():
                if result and isinstance(result, dict):
                    data_section = result.get("data", {})
                    current_span.set_attribute("retriever.has_data", bool(data_section))
                    if data_section:
                        metadata = data_section.get("metadatos", {})
                        current_span.set_attribute("retriever.titulo", metadata.get("titulo", "Unknown"))
                        current_span.set_attribute("retriever.fecha_publicacion", metadata.get("fecha_publicacion", "Unknown"))
        
        return result