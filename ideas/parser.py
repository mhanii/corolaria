@dataclass
class ConfiguracionEstructura:
    """Configuración de la estructura esperada para cada tipo de documento"""
    jerarquia: List[Dict[str, Any]]
    elementos_obligatorios: List[str]
    elementos_opcionales: List[str]

class ConfiguracionDocumentos:
    """Configuraciones para diferentes tipos de documentos legales"""
    
    @staticmethod
    def constitucion() -> ConfiguracionEstructura:
        return ConfiguracionEstructura(
            jerarquia=[
                {"tipo": "preambulo", "patron": r"^PREÁMBULO", "numeracion": None},
                {"tipo": "titulo", "patron": r"^TÍTULO\s+([IVXLCDM]+)", 
                 "numeracion": TipoNumeracion.ROMANO},
                {"tipo": "capitulo", "patron": r"^CAPÍTULO\s+([IVXLCDM]+)", 
                 "numeracion": TipoNumeracion.ROMANO},
                {"tipo": "seccion", "patron": r"^Sección\s+(\d+)\.?ª", 
                 "numeracion": TipoNumeracion.ORDINAL},
                {"tipo": "articulo", "patron": r"^Artículo\s+(\d+)", 
                 "numeracion": TipoNumeracion.ARABIGO},
                {"tipo": "apartado", "patron": r"^(\d+)\.", 
                 "numeracion": TipoNumeracion.ARABIGO},
                {"tipo": "letra", "patron": r"^([a-z])\)", 
                 "numeracion": TipoNumeracion.LETRA_MINUSCULA}
            ],
            elementos_obligatorios=["articulo"],
            elementos_opcionales=["preambulo", "titulo", "capitulo", "seccion"]
        )
    
    @staticmethod
    def codigo_penal() -> ConfiguracionEstructura:
        return ConfiguracionEstructura(
            jerarquia=[
                {"tipo": "libro", "patron": r"^LIBRO\s+([IVXLCDM]+)", 
                 "numeracion": TipoNumeracion.ROMANO},
                {"tipo": "titulo", "patron": r"^TÍTULO\s+([IVXLCDM]+)", 
                 "numeracion": TipoNumeracion.ROMANO},
                {"tipo": "capitulo", "patron": r"^CAPÍTULO\s+([IVXLCDM]+)", 
                 "numeracion": TipoNumeracion.ROMANO},
                {"tipo": "seccion", "patron": r"^Sección\s+(\d+)\.?ª", 
                 "numeracion": TipoNumeracion.ORDINAL},
                {"tipo": "articulo", "patron": r"^Artículo\s+(\d+)", 
                 "numeracion": TipoNumeracion.ARABIGO},
                {"tipo": "apartado", "patron": r"^(\d+)\.", 
                 "numeracion": TipoNumeracion.ARABIGO},
                {"tipo": "letra", "patron": r"^([a-z])\)", 
                 "numeracion": TipoNumeracion.LETRA_MINUSCULA}
            ],
            elementos_obligatorios=["libro", "articulo"],
            elementos_opcionales=["titulo", "capitulo", "seccion"]
        )
    
    @staticmethod
    def codigo_civil() -> ConfiguracionEstructura:
        return ConfiguracionEstructura(
            jerarquia=[
                {"tipo": "libro", "patron": r"^LIBRO\s+([IVXLCDM]+)", 
                 "numeracion": TipoNumeracion.ROMANO},
                {"tipo": "titulo", "patron": r"^TÍTULO\s+([IVXLCDM]+)", 
                 "numeracion": TipoNumeracion.ROMANO},
                {"tipo": "capitulo", "patron": r"^CAPÍTULO\s+([IVXLCDM]+)", 
                 "numeracion": TipoNumeracion.ROMANO},
                {"tipo": "seccion", "patron": r"^Sección\s+(\d+)\.?ª", 
                 "numeracion": TipoNumeracion.ORDINAL},
                {"tipo": "articulo", "patron": r"^Artículo\s+(\d+)", 
                 "numeracion": TipoNumeracion.ARABIGO},
                {"tipo": "apartado", "patron": r"^(\d+)\.", 
                 "numeracion": TipoNumeracion.ARABIGO}
            ],
            elementos_obligatorios=["libro", "articulo"],
            elementos_opcionales=["titulo", "capitulo", "seccion"]
        )
    
    @staticmethod
    def ley_simple() -> ConfiguracionEstructura:
        """Para leyes simples sin estructura compleja"""
        return ConfiguracionEstructura(
            jerarquia=[
                {"tipo": "capitulo", "patron": r"^CAPÍTULO\s+([IVXLCDM]+)", 
                 "numeracion": TipoNumeracion.ROMANO, "opcional": True},
                {"tipo": "articulo", "patron": r"^Artículo\s+(\d+)", 
                 "numeracion": TipoNumeracion.ARABIGO},
                {"tipo": "apartado", "patron": r"^(\d+)\.", 
                 "numeracion": TipoNumeracion.ARABIGO}
            ],
            elementos_obligatorios=["articulo"],
            elementos_opcionales=["capitulo"]
        )
