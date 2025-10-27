from typing import List, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime
import re



@dataclass
class Version:
    """Represents a version of content with metadata"""
    id_norma: Optional[str]
    fecha_publicacion: Optional[str]
    fecha_vigencia: Optional[str]
    content: List  # List of Elements


@dataclass
class Element:
    """An element from your XML parsing"""
    element_type: str  # 'p', 'blockquote', etc.
    content: str       # The actual text


@dataclass
class Node:
    """A node in the hierarchy tree"""
    name: str          # e.g., "I", "5", "1"
    level: int         # 1=TÍTULO, 2=CAPÍTULO, 3=Sección, 4=Artículo, 5=numbered, 6=lettered
    node_type: str     # "TÍTULO", "CAPÍTULO", "Artículo", etc.
    content: List[Union[str, 'Node']] = field(default_factory=list)
    parent: Optional['Node'] = None
    
    # Track which version this node came from
    version_id: Optional[str] = None
    fecha_vigencia: Optional[str] = None
    
    def add_child(self, child: 'Node') -> 'Node':
        """Add a child node to this node"""
        child.parent = self
        self.content.append(child)
        return child
    
    def add_text(self, text: str):
        """Add plain text to this node"""
        self.content.append(text)
    
    def get_full_name(self) -> str:
        """Get full name like 'TÍTULO I' or 'Artículo 5'"""
        if self.node_type == "Document":
            return "Document"
        return f"{self.node_type} {self.name}"
    
    def __repr__(self):
        return f"Node('{self.name}', level={self.level}, type={self.node_type})"


class SimpleParser:
    """Parse legal documents by detecting hierarchy levels"""
    
    # Patterns in order of hierarchy (higher number = deeper level)
    LEVELS = [
        (1, "TÍTULO", re.compile(r'^TÍTULO\s+(.+)', re.I)),
        (2, "CAPÍTULO", re.compile(r'^CAPÍTULO\s+(.+)', re.I)),
        (3, "Sección", re.compile(r'^Sección\s+(.+)', re.I)),
        (4, "Artículo", re.compile(r'^Artículo\s+(\d+)')),
        (5, "Apartado", re.compile(r'^(\d+)\.\s+(.+)')),  # Captures number AND text
        (6, "Subapartado", re.compile(r'^([a-z])\)\s+(.+)', re.I)),  # Captures letter AND text
    ]
    
    def __init__(self):
        self.root = Node("Document", level=0, node_type="Document")
        self.stack = [self.root]  # Stack of "currently open" nodes
    
    def detect_level(self, text: str) -> tuple[Optional[int], Optional[str], Optional[str], Optional[str]]:
        """
        Check if text is a hierarchy marker.
        Returns: (level, node_type, name, extra_text) or (None, None, None, None)
        
        Examples:
          "TÍTULO I" -> (1, "TÍTULO", "I", None)
          "Artículo 5" -> (4, "Artículo", "5", None)
          "1. España se..." -> (5, "Apartado", "1", "España se...")
          "Normal text" -> (None, None, None, None)
        """
        for level, node_type, pattern in self.LEVELS:
            match = pattern.match(text.strip())
            if match:
                name = match.group(1)
                # Check if there's a second capture group (the text after the marker)
                extra_text = match.group(2) if len(match.groups()) > 1 else None
                return level, node_type, name, extra_text
        return None, None, None, None
    
    def parse_version(self, version: Version) -> Node:
        """
        Takes ONE Version object and parses it into the tree.
        """
        for element in version.content:
            text = element.content.strip()
            if not text:
                continue
            
            level, node_type, name, extra_text = self.detect_level(text)
            
            if level is not None:
                # This is a hierarchy marker like "TÍTULO I" or "Artículo 5"
                
                # Pop the stack until we find a parent with lower level
                while self.stack[-1].level >= level:
                    self.stack.pop()
                
                # Create the new node
                node = Node(
                    name=name,
                    level=level,
                    node_type=node_type,
                    version_id=version.id_norma,
                    fecha_vigencia=version.fecha_vigencia
                )
                
                # Add it as a child of current top of stack
                self.stack[-1].add_child(node)
                
                # Push it onto stack (it's now the "current" node)
                self.stack.append(node)
                
                # If there's text after the marker (like "1. España se..."), add it
                if extra_text:
                    node.add_text(extra_text)
            else:
                # This is just regular text, not a hierarchy marker
                # Add it to whatever node is currently open (top of stack)
                self.stack[-1].add_text(text)
        
        return self.root
    
    def parse_versions(self, versions: List[Version]) -> Node:
        """
        Parse multiple versions into the same tree.
        Each version adds/updates nodes in the tree.
        """
        # Sort by fecha_vigencia to process in chronological order
        sorted_versions = sorted(
            versions, 
            key=lambda v: v.fecha_vigencia or "1900-01-01"
        )
        
        for version in sorted_versions:
            self.parse_version(version)
        
        return self.root
    
    def print_tree(self, node: Node = None, prefix: str = "", is_last: bool = True, show_versions: bool = False):
        """Print the tree structure with proper box-drawing characters"""
        if node is None:
            node = self.root
            print(f'{node.get_full_name()}')
            # Print children
            children = [item for item in node.content if isinstance(item, Node)]
            for i, child in enumerate(children):
                self.print_tree(child, "", i == len(children) - 1, show_versions)
            return
        
        # Print current node with full name and optional version info
        connector = "└─ " if is_last else "├─ "
        version_info = ""
        if show_versions and node.version_id:
            version_info = f" (v: {node.version_id}, vigencia: {node.fecha_vigencia})"
        print(f"{prefix}{connector}{node.get_full_name()}{version_info}")
        
        # Prepare prefix for children
        extension = "   " if is_last else "│  "
        new_prefix = prefix + extension
        
        # Collect children (both nodes and text)
        items = node.content
        
        for i, item in enumerate(items):
            is_last_item = (i == len(items) - 1)
            
            if isinstance(item, Node):
                # It's a child node - recurse
                self.print_tree(item, new_prefix, is_last_item, show_versions)
            else:
                # It's text - print it
                text_connector = "└─ " if is_last_item else "├─ "
                preview = item[:60] + "..." if len(item) > 60 else item
                print(f'{new_prefix}{text_connector}"{preview}"')


# Helper function to find nodes
def find_nodes_by_criteria(node: Node, **criteria) -> List[Node]:
    """
    Find all nodes matching criteria.
    
    Examples:
        find_nodes_by_criteria(tree, node_type="Artículo", name="13")
        find_nodes_by_criteria(tree, version_id="BOE-A-1992-20403")
    """
    results = []
    
    # Check if current node matches all criteria
    matches = all(getattr(node, key, None) == value for key, value in criteria.items())
    if matches:
        results.append(node)
    
    # Recurse through children
    for item in node.content:
        if isinstance(item, Node):
            results.extend(find_nodes_by_criteria(item, **criteria))
    
    return results


# Example usage
if __name__ == "__main__":
    # VERSION 1: Original constitution
    version1 = Version(
        id_norma="BOE-A-1978-31229",
        fecha_publicacion="1978-12-29",
        fecha_vigencia="1978-12-29",
        content=[
            Element('p', 'TÍTULO PRELIMINAR'),
            Element('p', 'Artículo 1'),
            Element('p', '1. España se constituye en un Estado social y democrático de Derecho...'),
            Element('p', '2. La soberanía nacional reside en el pueblo español...'),
            Element('p', '3. La forma política del Estado español es la Monarquía parlamentaria.'),
            Element('p', 'Artículo 2'),
            Element('p', 'La Constitución se fundamenta en la indisoluble unidad...'),
        ]
    )
    
    # VERSION 2: Amendment to Article 13 in 1992
    version2 = Version(
        id_norma="BOE-A-1992-20403",
        fecha_publicacion="1992-08-28",
        fecha_vigencia="1992-09-28",
        content=[
            Element('p', 'TÍTULO PRELIMINAR'),
            Element('p', 'Artículo 13'),
            Element('p', '1. Los extranjeros gozarán en España de las libertades públicas...'),
            Element('p', '2. Solamente los españoles serán titulares (MODIFICADO EN 1992)...'),
        ]
    )
    
    print("=" * 70)
    print("EXAMPLE 1: Parse single version")
    print("=" * 70)
    parser1 = SimpleParser()
    tree1 = parser1.parse_version(version1)
    parser1.print_tree(show_versions=True)
    
    print("\n" + "=" * 70)
    print("EXAMPLE 2: Parse multiple versions into same tree")
    print("=" * 70)
    parser2 = SimpleParser()
    tree2 = parser2.parse_versions([version1, version2])
    parser2.print_tree(show_versions=True)
    
    print("\n" + "=" * 70)
    print("EXAMPLE 3: Find all versions of Artículo 1")
    print("=" * 70)
    articles = find_nodes_by_criteria(tree2, node_type="Artículo", name="1")
    print(f"Found {len(articles)} version(s) of Artículo 1:")
    for art in articles:
        print(f"  - Version: {art.version_id}, Vigencia: {art.fecha_vigencia}")
        child_count = sum(1 for c in art.content if isinstance(c, Node))
        print(f"    Has {child_count} child nodes")
    
    print("\n" + "=" * 70)
    print("EXAMPLE 4: Clean view without version info")
    print("=" * 70)
    parser2.print_tree(show_versions=False)