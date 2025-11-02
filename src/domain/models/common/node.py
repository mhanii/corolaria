from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Union


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



@dataclass
class Node:
    """Base node for hierarchical document structure"""
    id: int
    name: str
    level: int
    node_type: NodeType

    content: List[Union[str, 'Node']] = None
    parent: Optional['Node'] = None

    path: Optional[str] = None 
    

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

     
    # def get_version_at_date(self, node: 'Node', date: str) -> Optional['Node']:
    #     """Get the version of a node that was active at a specific date."""
    #     date_dt = datetime.fromisoformat(date)
    #     current = node
        
    #     # Find the root version
    #     while current.previous_version:
    #         current = current.previous_version
        
    #     # Walk forward to find active version
    #     while current:
    #         vigencia = datetime.fromisoformat(current.fecha_vigencia) if current.fecha_vigencia else None
    #         caducidad = datetime.fromisoformat(current.fecha_caducidad) if current.fecha_caducidad else None
            
    #         # Check if this version is valid at target date
    #         if vigencia and vigencia <= date_dt:
    #             # If no caducidad or caducidad is after target date, this is the one
    #             if not caducidad or caducidad > date_dt:
    #                 return current
            
    #         current = current.next_version
        
    #     # No valid version at this date (node didn't exist yet or already removed)
    #     return None

    # def get_all_versions(self) -> List['Node']:
    #     """Get all versions of this node"""
    #     versions = [self]
    #     current = self
    #     while current.next_version:
    #         versions.append(current.next_version)
    #         current = current.next_version
    #     return versions
    
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
class StructureNode(Node):

    def __repr__(self):
        return super().__repr__()

@dataclass
class ArticleNode(Node):
    fecha_vigencia: Optional[str] = None
    fecha_caducidad: Optional[str] = None
    introduced_by: Optional[str] = None
    
    next_version: Optional[Node] = None
    previous_version: Optional[Node] = None

@dataclass
class ArticleElementNode(Node):
    other_parents: List['Node'] = field(default_factory=list)
    
    def compute_hash(self) -> int:
        """Compute hash based on node type, name, and text content"""
        text_content = tuple(
            item.strip() for item in self.content 
            if isinstance(item, str)
        )
        return hash((self.node_type, self.name, text_content))
    
    def merge_with(self, other: 'ArticleElementNode'):
        """Merge another element node into this one by adding its parent"""
        if other.parent and other.parent not in self.other_parents:
            self.other_parents.append(other.parent)