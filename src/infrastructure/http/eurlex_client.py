"""
EUR-Lex HTTP Client for EU document retrieval.

This module provides async clients for:
1. EUR-Lex SOAP Web Service (search with authentication)
2. CELLAR REST API (document/metadata retrieval)

Two-phase data retrieval:
1. SOAP search → returns CELLAR identifiers
2. REST retrieval → fetches documents by CELLAR ID/CELEX number
"""

import asyncio
import logging
import os
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass

import httpx
from lxml import etree

logger = logging.getLogger(__name__)


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class EURLexSearchResult:
    """Result from EUR-Lex SOAP search."""
    cellar_id: str
    celex_number: Optional[str] = None
    title: Optional[str] = None
    rank: int = 0


@dataclass
class EURLexDocument:
    """Document retrieved from CELLAR."""
    cellar_id: str
    celex_number: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    content: Optional[bytes] = None
    content_format: str = "xml"


class EURLexAuthenticationError(Exception):
    """Raised when EUR-Lex authentication fails."""
    pass


class EURLexSOAPError(Exception):
    """Raised when EUR-Lex returns a SOAP fault."""
    def __init__(self, message: str, fault_code: str = "", fault_detail: str = ""):
        super().__init__(message)
        self.fault_code = fault_code
        self.fault_detail = fault_detail


# =============================================================================
# SOAP Envelope Builder
# =============================================================================

class SOAPEnvelopeBuilder:
    """Builds SOAP envelopes with WS-Security for EUR-Lex."""
    
    # Namespaces
    NS = {
        'soap': 'http://www.w3.org/2003/05/soap-envelope',
        'sear': 'http://eur-lex.europa.eu/search',
        'wsse': 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd',
        'wsu': 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd',
    }
    
    PASSWORD_TYPE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordText"
    
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
    
    def build_search_envelope(
        self,
        expert_query: str,
        page: int = 1,
        page_size: int = 10,
        search_language: str = "es",
        exclude_consleg: bool = False,
        limit_latest_consleg: bool = False
    ) -> str:
        """
        Build SOAP envelope for EUR-Lex search request.
        
        Args:
            expert_query: EUR-Lex expert query syntax (e.g., "SELECT DN WHERE DN=32024R*")
            page: Page number (1-indexed)
            page_size: Results per page
            search_language: Language code (en, es, fr, etc.)
            exclude_consleg: Exclude consolidated versions
            limit_latest_consleg: Limit to latest consolidated version
            
        Returns:
            Complete SOAP envelope as XML string
        """
        # Build XML tree
        envelope = etree.Element(
            f"{{{self.NS['soap']}}}Envelope",
            nsmap={
                'soap': self.NS['soap'],
                'sear': self.NS['sear'],
            }
        )
        
        # Header with WS-Security
        header = etree.SubElement(envelope, f"{{{self.NS['soap']}}}Header")
        security = etree.SubElement(
            header,
            f"{{{self.NS['wsse']}}}Security",
            {f"{{{self.NS['soap']}}}mustUnderstand": "true"},
            nsmap={'wsse': self.NS['wsse'], 'wsu': self.NS['wsu']}
        )
        
        username_token = etree.SubElement(
            security,
            f"{{{self.NS['wsse']}}}UsernameToken",
            {f"{{{self.NS['wsu']}}}Id": "UsernameToken-1"}
        )
        
        username_el = etree.SubElement(username_token, f"{{{self.NS['wsse']}}}Username")
        username_el.text = self.username
        
        password_el = etree.SubElement(
            username_token,
            f"{{{self.NS['wsse']}}}Password",
            {"Type": self.PASSWORD_TYPE}
        )
        password_el.text = self.password
        
        # Body with search request
        body = etree.SubElement(envelope, f"{{{self.NS['soap']}}}Body")
        search_request = etree.SubElement(body, f"{{{self.NS['sear']}}}searchRequest")
        
        # Search parameters
        expert_query_el = etree.SubElement(search_request, f"{{{self.NS['sear']}}}expertQuery")
        expert_query_el.text = expert_query
        
        page_el = etree.SubElement(search_request, f"{{{self.NS['sear']}}}page")
        page_el.text = str(page)
        
        page_size_el = etree.SubElement(search_request, f"{{{self.NS['sear']}}}pageSize")
        page_size_el.text = str(page_size)
        
        language_el = etree.SubElement(search_request, f"{{{self.NS['sear']}}}searchLanguage")
        language_el.text = search_language
        
        if exclude_consleg:
            exclude_el = etree.SubElement(search_request, f"{{{self.NS['sear']}}}excludeAllConsleg")
            exclude_el.text = "true"
            
        if limit_latest_consleg:
            limit_el = etree.SubElement(search_request, f"{{{self.NS['sear']}}}limitToLatestConsleg")
            limit_el.text = "true"
        
        return '<?xml version="1.0" encoding="UTF-8"?>' + etree.tostring(envelope, encoding='unicode')


# =============================================================================
# EUR-Lex HTTP Client
# =============================================================================

class EURLexHTTPClient:
    """
    Async HTTP client for EUR-Lex SOAP Web Service and CELLAR REST API.
    
    Two-phase data retrieval:
    1. SOAP search → returns CELLAR identifiers
    2. REST retrieval → fetches documents by CELLAR ID
    
    Usage:
        async with EURLexHTTPClient() as client:
            results = await client.search("SELECT DN WHERE DN=32024R*")
            for result in results:
                doc = await client.get_document_content(result.cellar_id)
    """
    
    # Endpoints
    SOAP_URL = "https://eur-lex.europa.eu/EURLexWebService"
    CELLAR_BASE = "https://publications.europa.eu/resource/cellar"
    CELEX_BASE = "https://publications.europa.eu/resource/celex"
    # Public endpoint - no credentials required!
    EURLEX_HTML_BASE = "https://eur-lex.europa.eu/legal-content"
    
    # Config
    DEFAULT_TIMEOUT = 60.0
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_RETRY_DELAY = 2.0
    
    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY
    ):
        """
        Initialize EUR-Lex client.
        
        Args:
            username: ECAS username (defaults to EURLEX_USERNAME env var)
            password: Web service password (defaults to EURLEX_PASSWORD env var)
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
            retry_delay: Delay between retries (exponential backoff applied)
        """
        self.username = username or os.getenv("EURLEX_USERNAME", "")
        self.password = password or os.getenv("EURLEX_PASSWORD", "")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        self._client: Optional[httpx.AsyncClient] = None
        self._envelope_builder: Optional[SOAPEnvelopeBuilder] = None
    
    async def __aenter__(self):
        await self._ensure_client()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def _ensure_client(self):
        """Initialize HTTP client if not already done."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
            )
        if self._envelope_builder is None:
            self._envelope_builder = SOAPEnvelopeBuilder(self.username, self.password)
    
    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    # =========================================================================
    # SOAP Search
    # =========================================================================
    
    async def search(
        self,
        expert_query: str,
        page: int = 1,
        page_size: int = 10,
        language: str = "es"
    ) -> List[EURLexSearchResult]:
        """
        Execute EUR-Lex expert query via SOAP.
        
        Args:
            expert_query: Expert query syntax (e.g., "SELECT CELLAR_ID WHERE DN=32024R*")
            page: Page number (1-indexed)
            page_size: Results per page (max typically 100)
            language: Search language code
            
        Returns:
            List of search results with CELLAR IDs
            
        Example queries:
            "SELECT CELLAR_ID WHERE DN=32024R*"  # All 2024 regulations
            "SELECT DN, TI WHERE FM=REG AND DD>=2024-01-01"  # Recent regulations
        """
        await self._ensure_client()
        
        envelope = self._envelope_builder.build_search_envelope(
            expert_query=expert_query,
            page=page,
            page_size=page_size,
            search_language=language
        )
        
        logger.debug(f"EUR-Lex SOAP search: {expert_query[:100]}...")
        
        response = await self._soap_request(envelope)
        return self._parse_search_response(response)
    
    async def _soap_request(self, envelope: str) -> str:
        """Execute SOAP request with retries."""
        headers = {
            'Content-Type': 'application/soap+xml; charset=utf-8',
            'SOAPAction': '""'
        }
        
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.post(
                    self.SOAP_URL,
                    content=envelope.encode('utf-8'),
                    headers=headers
                )
                
                # Check for SOAP faults even with 500 status
                if response.status_code >= 400:
                    body = response.text
                    self._check_soap_fault(body)
                    # If no specific fault found, raise generic error
                    response.raise_for_status()
                
                return response.text
                
            except (EURLexAuthenticationError, EURLexSOAPError):
                # Don't retry auth errors
                raise
                
            except httpx.HTTPStatusError as e:
                logger.error(f"SOAP HTTP error {e.response.status_code}: {e}")
                raise
                
            except (httpx.RequestError, httpx.TimeoutException) as e:
                last_exception = e
                logger.warning(f"SOAP request failed (attempt {attempt + 1}): {e}")
                
                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
        
        raise RuntimeError(f"SOAP request failed after {self.max_retries + 1} attempts: {last_exception}")
    
    def _check_soap_fault(self, body: str):
        """Check response body for SOAP faults and raise appropriate exception."""
        if 'FailedAuthentication' in body:
            raise EURLexAuthenticationError(
                "EUR-Lex authentication failed. Please verify your credentials.\n"
                "Note: The web service password may differ from your ECAS password.\n"
                "Check your email for an approval message from EUR-Lex."
            )
        
        if 'Fault' in body and ('env:Fault' in body or 'soap:Fault' in body):
            # Try to extract fault message
            try:
                root = etree.fromstring(body.encode('utf-8'))
                reason = root.find('.//{http://www.w3.org/2003/05/soap-envelope}Text')
                fault_code = root.find('.//{http://www.w3.org/2003/05/soap-envelope}Value')
                raise EURLexSOAPError(
                    reason.text if reason is not None and reason.text else "Unknown SOAP fault",
                    fault_code=fault_code.text if fault_code is not None else ""
                )
            except etree.XMLSyntaxError:
                raise EURLexSOAPError("SOAP fault received (could not parse details)")
    
    def _parse_search_response(self, xml_response: str) -> List[EURLexSearchResult]:
        """Parse SOAP search response XML."""
        results = []
        
        try:
            root = etree.fromstring(xml_response.encode('utf-8'))
            
            # Find all result elements
            # Namespace-aware search
            ns = {'s': 'http://eur-lex.europa.eu/search'}
            
            for result in root.findall('.//s:result', ns) or root.findall('.//result'):
                cellar_id = None
                celex = None
                title = None
                rank = 0
                
                # Extract reference (CELLAR ID)
                ref = result.find('.//s:reference', ns) or result.find('.//reference')
                if ref is not None and ref.text:
                    cellar_id = ref.text.strip()
                    # Clean up format like "eng_cellar:uuid_en"
                    if 'cellar:' in cellar_id:
                        cellar_id = cellar_id.split('cellar:')[1].split('_')[0]
                
                # Extract rank
                rank_el = result.find('.//s:rank', ns) or result.find('.//rank')
                if rank_el is not None and rank_el.text:
                    rank = int(rank_el.text)
                
                # Extract CELEX from content if available
                content = result.find('.//s:content', ns) or result.find('.//content')
                if content is not None:
                    dn_el = content.find('.//DN') or content.find('.//s:DN', ns)
                    if dn_el is not None:
                        celex = dn_el.text if hasattr(dn_el, 'text') else str(dn_el)
                    
                    ti_el = content.find('.//EXPRESSION_TITLE//VALUE') or content.find('.//s:EXPRESSION_TITLE//VALUE', ns)
                    if ti_el is not None:
                        title = ti_el.text if hasattr(ti_el, 'text') else str(ti_el)
                
                if cellar_id:
                    results.append(EURLexSearchResult(
                        cellar_id=cellar_id,
                        celex_number=celex,
                        title=title,
                        rank=rank
                    ))
                    
        except etree.XMLSyntaxError as e:
            logger.error(f"Failed to parse SOAP response: {e}")
            raise
        
        logger.info(f"EUR-Lex search returned {len(results)} results")
        return results
    
    # =========================================================================
    # CELLAR REST API
    # =========================================================================
    
    async def get_branch_notice(
        self,
        cellar_id: str,
        language: str = "spa"
    ) -> Dict[str, Any]:
        """
        Retrieve branch notice (metadata) for a document.
        
        Branch notice contains metadata for a work, all its expressions,
        and corresponding manifestations.
        
        Args:
            cellar_id: CELLAR UUID
            language: Language code (eng, spa, fra, etc.)
            
        Returns:
            Parsed metadata dictionary
        """
        await self._ensure_client()
        
        url = f"{self.CELLAR_BASE}/{cellar_id}"
        headers = {
            'Accept': 'application/xml;notice=branch',
            'Accept-Language': language
        }
        
        response = await self._rest_request('GET', url, headers)
        return self._parse_notice_xml(response)
    
    async def get_document_content(
        self,
        identifier: str,
        format: str = "fmx4",
        language: str = "spa",
        use_celex: bool = True
    ) -> bytes:
        """
        Download document content in specified format.
        
        Args:
            identifier: CELEX number or CELLAR UUID
            format: Content format:
                - "fmx4": FORMEX XML (zip)
                - "pdf": PDF
                - "html": HTML
                - "xhtml": XHTML
            language: Language code (eng, spa, fra)
            use_celex: If True, uses CELEX endpoint (recommended)
            
        Returns:
            Raw content bytes
        """
        await self._ensure_client()
        
        if use_celex:
            url = f"{self.CELEX_BASE}/{identifier}"
        else:
            url = f"{self.CELLAR_BASE}/{identifier}"
        
        # Content type based on format
        accept_types = {
            'fmx4': 'application/zip;mtype=fmx4',
            'pdf': 'application/pdf',
            'html': 'text/html',
            'xhtml': 'application/xhtml+xml',
            'xml': 'application/xml'
        }
        
        headers = {
            'Accept': accept_types.get(format, format),
            'Accept-Language': language
        }
        
        logger.info(f"Fetching {identifier} in {format} format ({language})")
        
        return await self._rest_request('GET', url, headers, as_bytes=True)
    
    async def get_formex(
        self,
        celex_number: str,
        language: str = "spa"
    ) -> bytes:
        """
        Convenience method to get FORMEX XML content.
        
        Args:
            celex_number: CELEX number (e.g., "32024R1234")
            language: Language code
            
        Returns:
            FORMEX XML content (as zip bytes)
        """
        return await self.get_document_content(
            identifier=celex_number,
            format="fmx4",
            language=language,
            use_celex=True
        )
    
    async def get_html_content(
        self,
        celex_number: str,
        language: str = "ES"
    ) -> str:
        """
        Fetch document HTML from EUR-Lex public endpoint.
        
        **NO CREDENTIALS REQUIRED** - This uses the public EUR-Lex website.
        
        Args:
            celex_number: CELEX number (e.g., "32024R1689" for AI Act)
            language: 2-letter language code (ES, EN, FR, DE, etc.)
            
        Returns:
            HTML content as string
            
        Raises:
            httpx.HTTPStatusError: If document not found (404)
        """
        await self._ensure_client()
        
        # EUR-Lex public HTML endpoint
        url = f"{self.EURLEX_HTML_BASE}/{language.upper()}/TXT/HTML/?uri=CELEX:{celex_number}"
        
        logger.info(f"Fetching HTML (public): {celex_number} ({language})")
        
        response = await self._client.get(url)
        response.raise_for_status()
        
        logger.info(f"Retrieved {len(response.content)} bytes of HTML")
        return response.text
    
    async def get_document_public(
        self,
        celex_number: str,
        language: str = "ES",
        format: str = "HTML"
    ) -> str:
        """
        Fetch document from EUR-Lex public endpoint (no credentials needed).
        
        Supports multiple formats via the public website.
        
        Args:
            celex_number: CELEX number (e.g., "32024R1689")
            language: 2-letter language code
            format: Output format - HTML, TXT, PDF (PDF returns URL only)
            
        Returns:
            Document content as string (or PDF URL for PDF format)
        """
        await self._ensure_client()
        
        format_upper = format.upper()
        
        if format_upper == "PDF":
            # Return the PDF URL (can be downloaded separately)
            return f"{self.EURLEX_HTML_BASE}/{language}/TXT/PDF/?uri=CELEX:{celex_number}"
        
        url = f"{self.EURLEX_HTML_BASE}/{language}/TXT/{format_upper}/?uri=CELEX:{celex_number}"
        
        response = await self._client.get(url)
        response.raise_for_status()
        
        return response.text
    async def _rest_request(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        as_bytes: bool = False
    ):
        """Execute REST request with retries."""
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.request(
                    method=method,
                    url=url,
                    headers=headers
                )
                response.raise_for_status()
                
                if as_bytes:
                    return response.content
                return response.text
                
            except httpx.HTTPStatusError as e:
                logger.error(f"REST HTTP error {e.response.status_code} for {url}: {e}")
                raise
                
            except (httpx.RequestError, httpx.TimeoutException) as e:
                last_exception = e
                logger.warning(f"REST request failed (attempt {attempt + 1}): {e}")
                
                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
        
        raise RuntimeError(f"REST request failed after {self.max_retries + 1} attempts: {last_exception}")
    
    def _parse_notice_xml(self, xml_content: str) -> Dict[str, Any]:
        """Parse branch/tree notice XML to dictionary."""
        try:
            root = etree.fromstring(xml_content.encode('utf-8'))
            return self._xml_element_to_dict(root)
        except etree.XMLSyntaxError as e:
            logger.error(f"Failed to parse notice XML: {e}")
            raise
    
    def _xml_element_to_dict(self, element) -> Dict[str, Any]:
        """Recursively convert XML element to dictionary."""
        result = {}
        
        # Add attributes
        if element.attrib:
            for key, value in element.attrib.items():
                result[f"@{key}"] = value
        
        # Process children
        children = list(element)
        
        if children:
            child_dict = {}
            for child in children:
                tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                child_data = self._xml_element_to_dict(child)
                
                if tag in child_dict:
                    if not isinstance(child_dict[tag], list):
                        child_dict[tag] = [child_dict[tag]]
                    child_dict[tag].append(child_data)
                else:
                    child_dict[tag] = child_data
            
            result.update(child_dict)
        else:
            # Leaf element - just text
            if element.text and element.text.strip():
                return element.text.strip()
            return ""
        
        return result
    
    # =========================================================================
    # Health Check
    # =========================================================================
    
    async def health_check(self) -> bool:
        """
        Verify EUR-Lex web service is accessible.
        
        Returns:
            True if SOAP service responds correctly
        """
        try:
            # Simple search to verify connectivity
            results = await self.search(
                expert_query="SELECT DN WHERE DN=32024R0001",
                page=1,
                page_size=1
            )
            return True
        except Exception as e:
            logger.error(f"EUR-Lex health check failed: {e}")
            return False


# =============================================================================
# Convenience Function
# =============================================================================

async def create_eurlex_client(**kwargs) -> EURLexHTTPClient:
    """
    Create and initialize EUR-Lex client.
    
    Args:
        **kwargs: Arguments for EURLexHTTPClient
        
    Returns:
        Initialized client ready for use
    """
    client = EURLexHTTPClient(**kwargs)
    await client._ensure_client()
    return client
