from dataclasses import dataclass, field
from typing import List, Optional, Union
from datetime import datetime
from src.domain.models.common.base import Ambito, Materia, Departamento, Rango, EstadoConsolidacion,ElementType,BlockType,ReferenciaType
from src.domain.value_objects.relaciones_anteriores_model import RelacionesAnteriores
from src.domain.value_objects.relaciones_posteriores_model import RelacionesPosteriores
from .common.base import NoteType
from .common.node import NodeType,Node
from enum import Enum
import hashlib

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
    


    
    def get_hierarchy_path(self) -> List['Node']:
        """Get the path from root to this node"""
        path = []
        current = self
        while current:
            path.insert(0, current)
            current = current.parent
        return path
    
    def get_hierarchy_string(self) -> str:
        """Get a readable hierarchy path"""
        path = self.get_hierarchy_path()
        return " > ".join(f"{node.node_type}:{node.name}" for node in path)
    
    def get_full_name(self) -> str:
        """Get full name like 'TÍTULO I' or 'Artículo 5'"""
        if self.node_type == NodeType.ROOT:
            return "Document"
        return f"{self.node_type} {self.name}"
    
    def __repr__(self):
        return f"Node({self.node_type}, name='{self.name}', {self.content})"
    

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


@dataclass
class Version:
    id_norma: str
    fecha_publicacion: datetime
    fecha_vigencia: Optional[datetime]
    content: List[Element]


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


@dataclass
class Citation:
    text: str
    note_type: NoteType
    ref: str 