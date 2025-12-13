"""
EU Data Retriever pipeline step.

Fetches EU documents from EUR-Lex public HTML endpoint.
NO CREDENTIALS REQUIRED - uses the public website.
"""

import asyncio
import logging
from typing import Optional, Dict, Any

from src.application.pipeline.base import Step
from src.infrastructure.http.eurlex_client import EURLexHTTPClient

logger = logging.getLogger(__name__)


class EUDataRetriever(Step):
    """
    Retrieves EU documents from EUR-Lex public HTML endpoint.
    
    Uses the public website URL:
    https://eur-lex.europa.eu/legal-content/{lang}/TXT/HTML/?uri=CELEX:{celex}
    
    NO SOAP CREDENTIALS REQUIRED.
    
    Output format:
        {
            'html': str,        # HTML content
            'celex': str,       # CELEX number
            'language': str     # Language code
        }
    """
    
    def __init__(
        self,
        name: str = "eu_data_retriever",
        celex: Optional[str] = None,
        language: str = "ES"
    ):
        """
        Initialize EU data retriever.
        
        Args:
            name: Step name
            celex: CELEX number (e.g., "32016R0679" for RGPD, "12016P/TXT" for Charter)
            language: 2-letter language code (ES, EN, FR, DE, etc.)
        """
        super().__init__(name)
        self.celex = celex
        self.language = language.upper()
        self._client = None
    
    def _run_async(self, coro):
        """Run async coroutine from sync context."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Already in async context - create new loop
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(asyncio.run, coro).result()
            else:
                return loop.run_until_complete(coro)
        except RuntimeError:
            # No event loop - create one
            return asyncio.run(coro)
    
    def process(self, data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Fetch EU document HTML.
        
        Args:
            data: Optional input data (can override celex/language)
            
        Returns:
            Dictionary with:
            - 'html': HTML content string
            - 'celex': CELEX number
            - 'language': Language code
        """
        # Allow override from input data
        celex = self.celex
        language = self.language
        
        if data:
            celex = data.get('celex', celex)
            language = data.get('language', language)
        
        if not celex:
            logger.error("No CELEX number provided")
            return {}
        
        return self._run_async(self._fetch_html(celex, language))
    
    async def _fetch_html(self, celex: str, language: str) -> Dict[str, Any]:
        """Fetch HTML content from EUR-Lex public endpoint."""
        
        async with EURLexHTTPClient() as client:
            logger.info(f"Fetching EU document: {celex} ({language})")
            
            try:
                html_content = await client.get_html_content(celex, language)
                
                logger.info(f"Retrieved {len(html_content):,} bytes of HTML")
                
                return {
                    'html': html_content,
                    'celex': celex,
                    'language': language
                }
                
            except Exception as e:
                logger.error(f"Failed to fetch HTML for {celex}: {e}")
                return {
                    'html': None,
                    'celex': celex,
                    'language': language,
                    'error': str(e)
                }

