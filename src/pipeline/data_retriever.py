from .base import Step
from src.utils.http_client import BOEHTTPClient
import asyncio
import concurrent.futures

class DataRetriever(Step):
    def __init__(self, name: str, search_criteria: str = "default"): # For now you must specify the id.
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
        # Keep pipeline sync: run the async client call synchronously
        return self._run_coro_sync(self.client.get_law_by_id(self.search_criteria))