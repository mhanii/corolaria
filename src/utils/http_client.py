"""
Cliente HTTP para interactuar con la API del BOE.

Este módulo proporciona una interfaz asíncrona y robusta para realizar
peticiones a la API del Boletín Oficial del Estado.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Union   
from datetime import datetime
import json
from pydantic import BaseModel, Field,field_validator, model_validator
import httpx
from httpx import Response, RequestError, HTTPStatusError, TimeoutException
import re


logger = logging.getLogger(__name__)

class APIError(BaseModel):
    """Error de la API del BOE."""
    codigo: int = Field(..., description="Código de error HTTP")
    mensaje: str = Field(..., description="Mensaje de error")
    detalles: Optional[str] = Field(None, description="Detalles adicionales del error")
    timestamp: datetime = Field(default_factory=datetime.now, description="Momento del error")

    class Config:
        json_schema_extra = {
            "example": {
                "codigo": 404,
                "mensaje": "La información solicitada no existe",
                "detalles": "El identificador BOE-A-2025-99999 no se encontró",
                "timestamp": "2025-01-23T10:30:00Z"
            }
        }

class APIResponse(BaseModel):
    """Respuesta base de la API del BOE."""
    status: Dict[str, Union[str, int]] = Field(..., description="Estado de la respuesta")
    data: Optional[Any] = Field(None, description="Datos de la respuesta")

    @field_validator('status')
    def validate_status(cls, v):
        if 'code' not in v or 'text' not in v:
            raise ValueError("El status debe contener 'code' y 'text'")
        return v
    
class BOEHTTPClient:
    """
    Cliente HTTP asíncrono para la API del BOE.
    
    Maneja automáticamente:
    - Reintentos en caso de error
    - Timeouts configurables
    - Headers apropiados
    - Logging de peticiones
    - Parseo de respuestas XML/JSON
    """

    # URLs base de la API del BOE
    BASE_URL = "https://www.boe.es/datosabiertos/api"
    
    # Endpoints específicos
    ENDPOINTS = {
        'legislation': '/legislacion-consolidada',
        'boe_summary': '/boe/sumario',
        'borme_summary': '/borme/sumario',
        'auxiliary': '/tablas-auxiliares'
    }
    
    # Configuración por defecto
    DEFAULT_TIMEOUT = 30.0
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_RETRY_DELAY = 1.0

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY
    ):
        """
        Inicializa el cliente HTTP.
        
        Args:
            timeout: Timeout en segundos para las peticiones
            max_retries: Número máximo de reintentos
            retry_delay: Delay entre reintentos en segundos
            user_agent: User-Agent personalizado
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # Headers por defecto
        self.default_headers = {
            'Accept': 'application/json',  # Por defecto JSON
            'Accept-Charset': 'utf-8',
            'Accept-Encoding': 'gzip, deflate',
        }
        
        # Cliente HTTP reutilizable
        self._client: Optional[httpx.AsyncClient] = None
        


    async def __aenter__(self):
        """Entrada del context manager."""
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Salida del context manager."""
        await self.close()

    async def _ensure_client(self):
        """Asegura que el cliente HTTP esté inicializado."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                headers=self.default_headers,
                follow_redirects=True,
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
            )

    async def close(self):
        """Cierra el cliente HTTP."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _make_request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> Response:
        """
        Realiza una petición HTTP con reintentos.
        
        Args:
            method: Método HTTP (GET, POST, etc.)
            url: URL completa
            params: Parámetros de query string
            headers: Headers adicionales
            **kwargs: Argumentos adicionales para httpx
            
        Returns:
            Response de httpx
            
        Raises:
            APIError: Si la petición falla después de todos los reintentos
        """
        await self._ensure_client()
        
        # Combinar headers
        request_headers = self.default_headers.copy()
        if headers:
            request_headers.update(headers)
        
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                logger.debug(f"Intento {attempt + 1}/{self.max_retries + 1}: {method} {url}")
                
                response = await self._client.request(
                    method=method,
                    url=url,
                    params=params,
                    headers=request_headers,
                    **kwargs
                )
                
                # Log de la respuesta
                logger.debug(f"Respuesta: {response.status_code} para {url}")
                
                # Si la respuesta es exitosa, la devolvemos
                response.raise_for_status()
                return response
                
            except (RequestError, TimeoutException) as e:
                last_exception = e
                logger.warning(f"Error de red en intento {attempt + 1}: {e}")
                
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    
            except HTTPStatusError as e:
                # Errores HTTP no se reintentan (4xx, 5xx)
                logger.error(f"Error HTTP {e.response.status_code}: {e}")
                raise APIError(
                    codigo=e.response.status_code,
                    mensaje=f"Error HTTP {e.response.status_code}",
                    detalles=str(e),
                    timestamp=datetime.now()
                )
        
        # Si llegamos aquí, fallaron todos los reintentos
        raise APIError(
            codigo=500,
            mensaje="Error de conexión después de varios reintentos",
            detalles=str(last_exception),
            timestamp=datetime.now()
        )

    async def get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        accept_format: str = "application/json"
    ) -> Dict[str, Any]:
        """
        Realiza una petición GET a la API del BOE.
        
        Args:
            endpoint: Endpoint de la API (relativo a BASE_URL)
            params: Parámetros de query string
            accept_format: Formato de respuesta deseado
            
        Returns:
            Datos de la respuesta parseados
            
        Raises:
            APIError: Si hay error en la petición o parseo
        """
        url = f"{self.BASE_URL}{endpoint}"
        
        headers = {
            'Accept': accept_format
        }
        
        response = await self._make_request(
            method="GET",
            url=url,
            params=params,
            headers=headers
        )
        
        return await self._parse_response(response, accept_format)

    async def _parse_response(
        self, 
        response: Response, 
        accept_format: str
    ) -> Dict[str, Any]:
        """
        Parsea la respuesta según el formato solicitado.
        
        Args:
            response: Respuesta HTTP
            accept_format: Formato esperado
            
        Returns:
            Datos parseados
            
        Raises:
            APIError: Si hay error en el parseo
        """
        try:
            content = response.text
            
            if accept_format == "application/json":
                return json.loads(content)
                
            elif accept_format == "application/xml":
                # Para XML, necesitaremos parsearlo con lxml
                from lxml import etree
                root = etree.fromstring(content.encode('utf-8'))
                return self._xml_to_dict(root)
                
            else:
                raise APIError(
                    codigo=400,
                    mensaje=f"Formato no soportado: {accept_format}",
                    timestamp=datetime.now()
                )
                
        except (json.JSONDecodeError, etree.XMLSyntaxError) as e:
            raise APIError(
                codigo=500,
                mensaje="Error parseando respuesta de la API",
                detalles=str(e),
                timestamp=datetime.now()
            )

    def _xml_to_dict(self, element) -> Dict[str, Any]:
        """
        Convierte un elemento XML a diccionario.
        
        Maneja los atributos del XML, estructura jerárquica,
        y asegura que ciertos elementos sean listas.
        
        Además, aplana contenedores específicos:
        <anteriores><anterior>...</anterior></anteriores> → [ {...}, {...} ]
        """
        list_fields = {"materia", "anterior", "posterior","bloque","version"}
        flatten_containers = {"materias", "anteriores", "posteriores"}

        result = {}

        # Añadir atributos
        if element.attrib:
            for key, value in element.attrib.items():
                result[f"@{key}"] = value

        # Procesar hijos
        children = list(element)
        if children:
            child_dict = {}
            for child in children:
                tag = child.tag
                child_data = self._xml_to_dict(child)

                # Forzar listas en campos definidos
                if tag in list_fields:
                    child_dict.setdefault(tag, []).append(child_data)
                else:
                    if tag in child_dict:
                        if not isinstance(child_dict[tag], list):
                            child_dict[tag] = [child_dict[tag]]
                        child_dict[tag].append(child_data)
                    else:
                        child_dict[tag] = child_data

            # Si hay texto además de hijos
            if element.text and element.text.strip():
                child_dict["text"] = element.text.strip()

            # 🔹 Aplanar contenedores específicos
            if element.tag in flatten_containers:
                for lf in list_fields:
                    if lf in child_dict:
                        return child_dict[lf]

            result.update(child_dict)
        else:
            # Elemento sin hijos: solo texto
            result = element.text.strip() if element.text else ""

        # ✅ Solo normalizar si result es un dict
        if isinstance(result, dict):
            for field in list_fields:
                if field in result and not isinstance(result[field], list):
                    result[field] = [result[field]]

        return result



    # ========================================================================
    # MÉTODOS ESPECÍFICOS PARA CADA ENDPOINT
    # ========================================================================

    async def search_legislation(
        self,
        query: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Busca en la legislación consolidada.
        
        Args:
            query: Consulta de búsqueda JSON
            from_date: Fecha inicio (AAAAMMDD)
            to_date: Fecha fin (AAAAMMDD)
            offset: Primer resultado
            limit: Número máximo de resultados
            **kwargs: Parámetros adicionales
            
        Returns:
            Resultados de la búsqueda
        """
        params = {
            'offset': offset,
            'limit': limit
        }
        
        if query:
            params['query'] = query
        if from_date:
            params['from'] = from_date
        if to_date:
            params['to'] = to_date
            
        # Añadir parámetros adicionales
        params.update(kwargs)
        
        return await self.get(
            endpoint=self.ENDPOINTS['legislation'],
            params=params
        )

    async def get_law_by_id(
        self,
        law_id: str,
        section: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Obtiene una norma específica por su ID.
        
        Args:
            law_id: Identificador de la norma (ej: BOE-A-2015-10566)
            section: Sección específica (metadatos, analisis, texto, etc.)
            
        Returns:
            Datos de la norma
        """
        endpoint = f"{self.ENDPOINTS['legislation']}/id/{law_id}"
        
        if section:
            endpoint += f"/{section}"
            
        return await self.get(endpoint=endpoint,accept_format="application/xml")

    async def get_boe_summary(
        self,
        date: str
    ) -> Dict[str, Any]:
        """
        Obtiene el sumario del BOE para una fecha.
        
        Args:
            date: Fecha en formato AAAAMMDD
            
        Returns:
            Sumario del BOE
        """
        endpoint = f"{self.ENDPOINTS['boe_summary']}/{date}"
        return await self.get(endpoint=endpoint)

    async def get_borme_summary(
        self,
        date: str
    ) -> Dict[str, Any]:
        """
        Obtiene el sumario del BORME para una fecha.
        
        Args:
            date: Fecha en formato AAAAMMDD
            
        Returns:
            Sumario del BORME
        """
        endpoint = f"{self.ENDPOINTS['borme_summary']}/{date}"
        return await self.get(endpoint=endpoint)

    async def get_auxiliary_table(
        self,
        table_name: str
    ) -> Dict[str, Any]:
        """
        Obtiene una tabla auxiliar.
        
        Args:
            table_name: Nombre de la tabla (departamentos, rangos, etc.)
            
        Returns:
            Datos de la tabla auxiliar
        """
        endpoint = f"{self.ENDPOINTS['auxiliary']}/{table_name}"
        return await self.get(endpoint=endpoint)

    # ========================================================================
    # MÉTODOS DE CONVENIENCIA
    # ========================================================================

    async def health_check(self) -> bool:
        """
        Verifica si la API del BOE está disponible.
        
        Returns:
            True si la API responde correctamente
        """
        try:
            # Hacemos una búsqueda mínima para verificar conectividad
            await self.search_legislation(limit=1)
            return True
        except APIError:
            return False

    def build_search_query(
        self,
        text: Optional[str] = None,
        title: Optional[str] = None,
        department: Optional[str] = None,
        legal_range: Optional[str] = None,
        matter: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> str:
        """
        Construye una consulta de búsqueda estructurada.
        
        Args:
            text: Búsqueda en texto completo
            title: Búsqueda en título
            department: Código de departamento
            legal_range: Código de rango normativo
            matter: Código de materia
            date_from: Fecha desde
            date_to: Fecha hasta
            
        Returns:
            Query JSON para la API
        """
        query_parts = []
        
        if text:
            query_parts.append(f'texto:"{text}"')
        if title:
            query_parts.append(f'titulo:"{title}"')
        if department:
            query_parts.append(f'departamento@codigo:{department}')
        if legal_range:
            query_parts.append(f'rango@codigo:{legal_range}')
        if matter:
            query_parts.append(f'materia@codigo:{matter}')
            
        query_string = " AND ".join(query_parts) if query_parts else ""
        
        query_json = {
            "query": {
                "query_string": {"query": query_string}
            }
        }
        
        if date_from or date_to:
            date_range = {}
            if date_from:
                date_range["gte"] = date_from
            if date_to:
                date_range["lte"] = date_to
            query_json["query"]["range"] = {
                "fecha_publicacion": date_range
            }
        
        return json.dumps(query_json, ensure_ascii=False)


# ============================================================================
# FUNCIÓN DE CONVENIENCIA
# ============================================================================

async def create_boe_client(**kwargs) -> BOEHTTPClient:
    """
    Crea y configura un cliente BOE.
    
    Args:
        **kwargs: Argumentos para BOEHTTPClient
        
    Returns:
        Cliente configurado y listo para usar
    """
    client = BOEHTTPClient(**kwargs)
    await client._ensure_client()
    return client