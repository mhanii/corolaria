from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime
from src.models.ambitos_model import Ambitos
from src.models.materias_model import Materias
from src.models.departamentos_model import Departamentos
from src.models.rangos_model import Rangos
from src.models.estados_consolidacion_model import EstadosConsolidacion
from src.models.relaciones_anteriores_model import RelacionesAnteriores
from src.models.relaciones_posteriores_model import RelacionesPosteriores
from enum import Enum
from typing import Optional

@dataclass
class Ambito:
    id: int

    def get_code(self) -> int:
        """Get the code of the ambito."""
        return self.id
    
    def get_name(self) -> Optional[str]:
        """Get the name of the ambito using the Ambitos model."""
        return Ambitos.name_from_code(self.id)
    
    def is_valid(self) -> bool:
        """Check if the ambito ID is valid."""
        return self.get_name() is not None
    
@dataclass
class Materia:
    id: int

    def get_code(self) -> int:
        """Get the code of the materia."""
        return self.id
    
    def get_name(self) -> Optional[str]:
        """Get the name of the materia using the Materias model."""
        return Materias.name_from_code(self.id)
    
    def is_valid(self) -> bool:
        """Check if the materia ID is valid."""
        return self.get_name() is not None
    
@dataclass
class Departamento:
    id: int

    def get_code(self) -> int:
        """Get the code of the departamento."""
        return self.id
    
    def get_name(self) -> Optional[str]:
        """Get the name of the departamento using the Departamentos model."""
        return Departamentos.name_from_code(self.id)
    
    def is_valid(self) -> bool:
        """Check if the departamento ID is valid."""
        return self.get_name() is not None

@dataclass
class Rango:
    id: int

    def get_code(self) -> int:
        """Get the code of the rango."""
        return self.id
    
    def get_name(self) -> Optional[str]:
        """Get the name of the rango using the Rangos model."""
        return Rangos.name_from_code(self.id)
    
    def is_valid(self) -> bool:
        """Check if the rango ID is valid."""
        return self.get_name() is not None
    
@dataclass
class EstadoConsolidacion:
    id: int

    def get_code(self) -> int:
        """Get the code of the estado de consolidacion."""
        return self.id
    
    def get_name(self) -> Optional[str]:
        """Get the name of the estado de consolidacion using the EstadosConsolidacion model."""
        return EstadosConsolidacion.name_from_code(self.id)
    
    def is_valid(self) -> bool:
        """Check if the estado de consolidacion ID is valid."""
        return self.get_name() is not None
    



class ElementType(str,Enum):
    PARAGRAPH = "p"
    TABLE = "table"
    BLOCKQUOTE = "blockquote" 
    IMG = "img"
    def __str__(self):
        return self.value


class BlockType(str,Enum):
    NOTA_INICIAL = "nota_inicial"
    PRECEPTO = "precepto"
    ENCABEZADO = "encabezado"
    CABECERA = "cabecera"
    FIRMA = "firma"
    PARTE_DISPOSITIVA = "parte_dispositiva"
    PARTE_FINAL = "parte_final"
    PREAMBULO = "preambulo"
    INSTRUMENTO = "instrumento"
    # This needs more thinking
    def __str__(self):
        return self.value

class NodeType(str,Enum):
    """Types of nodes in the document hierarchy"""
    ROOT = "root"
    LIBRO = "libro"
    TITULO = "titulo"
    CAPITULO = "capitulo"
    SECCION = "seccion"
    SUBSECCION = "subseccion"
    ARTICULO = "articulo"
    ARTICULO_UNICO = "articulo_unico"
    APARTADO_ALFA = "apartado_alfa"
    APARTADO_NUMERICO = "apartado_numerico"
    PARRAFO = "parrafo"
    ORDINAL_ALFA = "ordinal_alfa"
    ORDINAL_NUMERICO = "ordinal_numerico"
    DISPOSICION = "disposicion"

    DELETED = "deleted"  # For removed nodes

class ReferenciaType(str,Enum):
    ANTERIOR = "anterior"
    POSTERIOR = "posterior"

    def __str__(self):
        return self.value



class ChangeType(str,Enum):
    ADDED = "added"
    REMOVED = "removed"
    REPLACED = "replaced"


class NoteType(str,Enum):
    CITATION = "cita_con_pleca"