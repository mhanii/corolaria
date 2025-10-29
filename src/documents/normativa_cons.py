from dataclasses import dataclass, field
from typing import List, Optional, Union
from datetime import datetime
from src.models.ambitos_model import Ambitos
from src.models.materias_model import Materias
from src.documents.base import Ambito, Materia, Departamento, Rango, EstadoConsolidacion,ElementType,BlockType,ReferenciaType
from src.models.relaciones_anteriores_model import RelacionesAnteriores
from src.models.relaciones_posteriores_model import RelacionesPosteriores
from .base import NodeType, ChangeType, NoteType

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
    

@dataclass
class Node:
    """Base node for hierarchical document structure"""
    id: int
    name: str
    level: int

    node_type: NodeType

    version_index: int = 0 # 0 for original, 1..n for versions

    content: List[Union[str, 'Node']] = None
    parent: Optional['Node'] = None


    path: Optional[str] = None 


    fecha_vigencia: Optional[str] = None
    fecha_caducidad: Optional[str] = None
    
    # Version chain
    next_version: Optional['Node'] = None
    previous_version: Optional['Node'] = None
    
    # Link to change event (only if not original)
    created_by_change: Optional[str] = None  # ChangeEvent ID
    change_type: Optional[ChangeType] = None

    def __post_init__(self):
        if self.content is None:
            self.content = []
    
    def add_child(self, child: 'Node') -> 'Node':
        """Add a child node and set its parent reference"""
        child.parent = self
        self.content.append(child)
        return child
    
    def add_text(self, text: str):
        """Add plain text to this node"""
        self.content.append(text)


    def create_next_version(
        self, 
        new_content: List[Union[str, 'Node']],
        change_event_id: str,
        change_type: ChangeType,
        fecha_vigencia: datetime
    ) -> 'Node':
        """Create a new version of this node"""
        new_version = Node(
            id=self.id,
            name=self.name,
            level=self.level,
            node_type=self.node_type,
            content=new_content,
            parent=self.parent,
            version_index=self.version_index + 1,
            fecha_vigencia=fecha_vigencia,
            created_by_change=change_event_id,
            change_type=change_type,
            previous_version=self
        )
        self.next_version = new_version
        self.fecha_caducidad = fecha_vigencia
        return new_version
     
    def get_version_at_date(self, node: 'Node', date: str) -> Optional['Node']:
        """Get the version of a node that was active at a specific date."""
        date_dt = datetime.fromisoformat(date)
        current = node
        
        # Find the root version
        while current.previous_version:
            current = current.previous_version
        
        # Walk forward to find active version
        while current:
            vigencia = datetime.fromisoformat(current.fecha_vigencia) if current.fecha_vigencia else None
            caducidad = datetime.fromisoformat(current.fecha_caducidad) if current.fecha_caducidad else None
            
            # Check if this version is valid at target date
            if vigencia and vigencia <= date_dt:
                # If no caducidad or caducidad is after target date, this is the one
                if not caducidad or caducidad > date_dt:
                    return current
            
            current = current.next_version
        
        # No valid version at this date (node didn't exist yet or already removed)
        return None

    def get_all_versions(self) -> List['Node']:
        """Get all versions of this node"""
        versions = [self]
        current = self
        while current.next_version:
            versions.append(current.next_version)
            current = current.next_version
        return versions
    
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
        version_info = f"v{self.version_index}" if not self.version_index > 0 else "original"
        return f"Node({self.node_type}, name='{self.name}', {version_info})"
    


@dataclass
class ChangeEvent:
    """Represents all changes made to ONE document by ONE legislative act"""
    id: str  # Hash of target + source document IDs
    
    # The document being changed
    target_document_id: str
    
    # The document making the change
    source_document_id: str
    
    # When it takes effect
    fecha_vigencia: datetime
    
    # Optional human-readable summary
    description: Optional[str] = None
    
    # Affected nodes (populated during parsing)
    affected_nodes: List[str] = field(default_factory=list)  # Node paths
    
    @staticmethod
    def generate_id(target_doc_id: str, source_doc_id: str) -> str:
        """
        Generate deterministic ID from target and source document IDs.
        This allows merging multiple changes from same source to same target.
        """
        combined = f"{target_doc_id}:{source_doc_id}"
        hash_object = hashlib.sha256(combined.encode())
        return f"change_{hash_object.hexdigest()[:16]}"
    
    @classmethod
    def create(
        cls,
        target_document_id: str,
        source_document_id: str,
        fecha_vigencia: datetime,
        description: Optional[str] = None
    ) -> 'ChangeEvent':
        """Factory method to create a ChangeEvent with proper ID"""
        change_id = cls.generate_id(target_document_id, source_document_id)
        return cls(
            id=change_id,
            target_document_id=target_document_id,
            source_document_id=source_document_id,
            fecha_vigencia=fecha_vigencia,
            description=description
        )
    
    def add_affected_node(self, node_path: str):
        """Add a node that was affected by this change"""
        if node_path not in self.affected_nodes:
            self.affected_nodes.append(node_path)
    
    def __repr__(self):
        return (f"ChangeEvent(id={self.id[:12]}..., "
                f"target={self.target_document_id}, "
                f"source={self.source_document_id}, "
                f"affects={len(self.affected_nodes)} nodes)")

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


@dataclass
class Citation:
    text: str
    note_type: NoteType
    ref: str 