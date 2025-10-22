from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime
from src.models.ambitos_model import Ambitos
from src.models.materias_model import Materias
from src.documents.base import Ambito, Materia, Departamento, Rango, EstadoConsolidacion,ElementType,BlockType,ReferenciaType
from src.models.relaciones_anteriores_model import RelacionesAnteriores
from src.models.relaciones_posteriores_model import RelacionesPosteriores


@dataclass
class Metadata:
    fecha_actualizacion: datetime
    id: str
    ambito: Ambito
    departamento: Departamento
    titulo: str
    rango: Rango
    fecha_disposicion: datetime
    diario: str
    fecha_publicacion: datetime
    diario_numero: str
    fecha_vigencia: Optional[datetime]
    estatus_derogacion: bool
    estatus_anulacion: bool
    vigencia_agotada: bool
    estado_consolidacion: EstadoConsolidacion
    url_eli: str
    url_html_consolidado: str





@dataclass
class Referencia:
    id_norma: str
    type: ReferenciaType
    relacion: int
    text: str

    def get_code(self) -> int:
        """Get the code of the relacion posterior."""
        return self.id
    def get_name(self) -> Optional[str]:
        """Get the name of the relacion using the RelacionesPosteriores or RelacionesAnteriores model."""
        if self.type == ReferenciaType.ANTERIOR:
            return RelacionesAnteriores.name_from_code(self.id)
        else:   
            return RelacionesPosteriores.name_from_code(self.id)
        
    def is_valid(self) -> bool:
        """Check if the relacion posterior ID is valid."""
        return self.get_name() is not None
    


@dataclass
class Analysis:
    materias: List[Materia]  
    referencias_anteriores: List[Referencia]  # Using RelacionesAnteriores model
    referencias_posteriores: List[Referencia]  # Using RelacionesPosteriores model



@dataclass
class Element:
    """Base class for document elements."""
    element_type: ElementType
    content: Optional[str] = None

    def get_type(self) -> ElementType:
        """Get the type of the element."""
        return self.element_type
    
    # def __str__(self):
    #     return f"""
    #     Elements(element_type={self.element_type}, content={self.content})"""


@dataclass
class Version:
    id_norma: str
    fecha_publicacion: datetime
    fecha_vigencia: Optional[datetime]
    content: List[Element]

    # def __str__(self):
    #     return f"""
    #     Version(id_norma={self.id_norma}, fecha_publicacion={self.fecha_publicacion},
    #     fecha_vigencia={self.fecha_vigencia},content={self.content})"""

@dataclass
class Block:
    id: str
    type: BlockType
    title: Optional[str]
    versions: List[Version]

    # def __str__(self):
    #     return f"""
    #     Block(id={self.id}, type={self.type}, title={self.title},
    #     versions={self.versions})"""


@dataclass
class NormativaCons:
    id: str
    metadata: Metadata
    analysis: Analysis
    blocks: List[Block]


