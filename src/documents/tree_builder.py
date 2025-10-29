from typing import List, Optional, Union, Dict, Tuple, Set
from datetime import datetime
from dataclasses import dataclass
import re
import hashlib
import difflib
from .normativa_cons import ChangeEvent, Node, Version
from .base import ChangeType, NodeType,NoteType,ElementType
# Assuming these are imported from your modules
# from .base import ElementType, NodeType, ChangeType, NoteType
# from .normativa_cons import Element, Node, ChangeEvent, Version

from typing import List, Optional, Union, Dict, Tuple, Set
from datetime import datetime
from dataclasses import dataclass
import re

# Assuming these are imported from your modules
# from .base import ElementType, NodeType, ChangeType, NoteType
# from .normativa_cons import Element, Node, ChangeEvent, Version


class EnhancedTreeBuilder:
    """
    Enhanced TreeBuilder with simplified path-based tracking.
    
    Key improvements:
    1. Only includes paragraph numbers in paths for direct article children
    2. When structure changes (paragraph -> apartado), old nodes are marked as REMOVED
    3. Simple path-based tracking
    """
    
    LEVELS = [
        (0, NodeType.DISPOSICION, re.compile(r'^Disposición\s+(.+)', re.I)),
        (0, NodeType.LIBRO, re.compile(r'^LIBRO\s+(.+)', re.I)),
        (1, NodeType.TITULO, re.compile(r'^TÍTULO\s+(.+)', re.I)),
        (2, NodeType.CAPITULO, re.compile(r'^CAPÍTULO\s+(.+)', re.I)),
        (3, NodeType.SECCION, re.compile(r'^Sección\s+(\d+\.ª)(?:\s*\.?\s*(.*))?', re.I)),
        (4, NodeType.SUBSECCION, re.compile(r'^Subsección\s+(\d+ª)(?:\s*\.?\s*(.*))?', re.I)),
        (5, NodeType.ARTICULO_UNICO, re.compile(r'^Artículo\s+único(?:\s*\.?\s*(.*))?', re.I)),
        (5, NodeType.ARTICULO, re.compile(r'^Artículo\s+(\d+(?:\s+(?:bis|ter|quater|quinquies|sexies|septies|octies|novies|decies|[A-Za-z]))?)', re.I)),
        (6, NodeType.APARTADO_NUMERICO, re.compile(r'^(\d+)\.\s+(.+)')),
        (7, NodeType.PARRAFO, re.compile(r'^\s*(.+)')),
        (8, NodeType.APARTADO_ALFA, re.compile(r'^([a-z])\)\s+(.+)', re.I)),
        (8, NodeType.ORDINAL_ALFA, re.compile(r'^(\d+\.+ª)\s*(.*)$', re.I)),
        (8, NodeType.ORDINAL_NUMERICO, re.compile(r'^(\d+\.+º)\s*(.*)$', re.I)),
    ]

    def __init__(self, target_document_id: str):
        self.target_document_id = target_document_id
        self.root = Node(
            name="Content", 
            level=-1, 
            node_type=NodeType.ROOT, 
            id=0,
            version_index=0,
            path="root"
        )
        self.stack = [self.root]
        
        # Path -> Latest version of that node
        self.node_registry: Dict[str, Node] = {"root": self.root}
        
        # Track paths from previous version (to detect removals)
        self.previous_version_paths: Set[str] = set()
        
        # Track paths in current version being parsed
        self.current_version_paths: Set[str] = set()
        
        # Change events tracking
        self.change_events: Dict[str, ChangeEvent] = {}
        
        # Counters
        self.next_node_id = 1
        self.paragraph_counter = 0

    def _should_include_in_path(self, node_type: NodeType, parent: Node) -> bool:
        """
        Determine if a node type should be included in the path.
        
        Rule: Include PARRAFO in path only if direct child of ARTICULO
        """
        if node_type == NodeType.PARRAFO:
            # Only include if parent is an article
            return parent.node_type in (NodeType.ARTICULO, NodeType.ARTICULO_UNICO)
        
        # Always include other node types
        return True

    def _get_node_path(self, node: Node) -> str:
        """
        Generate path following the rules:
        - Paragraphs only appear in path if direct children of articles
        - Other nodes always included
        """
        if node.path:
            return node.path
        
        path_parts = []
        current = node
        
        while current and current.node_type != NodeType.ROOT:
            # Check if this node should be included in path
            if current.parent and self._should_include_in_path(current.node_type, current.parent):
                if current.name:
                    path_parts.insert(0, f"{current.node_type.value}_{current.name}")
            current = current.parent
        
        return "/".join(path_parts) if path_parts else "root"

    def _find_node_by_path(self, path: str) -> Optional[Node]:
        """Find the latest version of a node by its path"""
        return self.node_registry.get(path)

    def _register_node(self, node: Node):
        """Register a node in the registry"""
        if not node.path:
            node.path = self._get_node_path(node)
        self.node_registry[node.path] = node

    def _extract_content_from_node(self, node: Node) -> List[str]:
        """Extract all text content from a node (excluding child nodes)"""
        content = []
        for item in node.content:
            if isinstance(item, str):
                content.append(item.strip())
        return content

    def _compare_node_content(
        self, 
        old_node: Optional[Node], 
        new_content: List[str]
    ) -> Tuple[bool, ChangeType]:
        """
        Compare node content and determine if it changed.
        Returns (has_changed, change_type)
        """
        if old_node is None:
            return True, ChangeType.ADDED
        
        old_content = self._extract_content_from_node(old_node)
        
        if not old_content and not new_content:
            return False, None
            
        if not old_content:
            return True, ChangeType.ADDED
            
        if not new_content:
            return True, ChangeType.REMOVED
        
        if old_content != new_content:
            return True, ChangeType.REPLACED
            
        return False, None

    def _get_or_create_change_event(
        self, 
        source_document_id: str, 
        fecha_vigencia: datetime,
        description: Optional[str] = None
    ) -> ChangeEvent:
        """Get existing or create new ChangeEvent for a source document"""
        change_id = ChangeEvent.generate_id(self.target_document_id, source_document_id)
        
        if change_id not in self.change_events:
            self.change_events[change_id] = ChangeEvent.create(
                target_document_id=self.target_document_id,
                source_document_id=source_document_id,
                fecha_vigencia=fecha_vigencia,
                description=description
            )
        
        return self.change_events[change_id]

    def _create_or_update_node(
        self,
        parent: Node,
        level: int,
        node_type: NodeType,
        name: str,
        content_text: Optional[str],
        version: Version,
        version_index: int,
        change_event: Optional[ChangeEvent] = None
    ) -> Node:
        """
        Create a new node or update existing one if content changed.
        Simple path-based approach.
        """
        # Create temporary node to calculate path
        temp_node = Node(
            id=-1, name=name, level=level, node_type=node_type,
            version_index=-1, parent=parent, path=""
        )
        node_path = self._get_node_path(temp_node)
        
        # Track this path as seen in current version
        self.current_version_paths.add(node_path)
        
        # Find existing node by path
        existing_node = self._find_node_by_path(node_path)
        
        # Prepare content
        new_content = [content_text] if content_text else []
        
        # Compare content
        has_changed, change_type = self._compare_node_content(existing_node, new_content)
        
        if existing_node is None:
            # Brand new node
            new_node = Node(
                id=self.next_node_id,
                name=name,
                level=level,
                node_type=node_type,
                content=new_content.copy(),
                parent=parent,
                version_index=version_index,
                path=node_path,
                fecha_vigencia=version.fecha_vigencia,
                created_by_change=change_event.id if change_event else None,
                change_type=ChangeType.ADDED if change_event else None
            )
            self.next_node_id += 1
            parent.add_child(new_node)
            self._register_node(new_node)
            
            if change_event:
                change_event.add_affected_node(node_path)
            
            return new_node
            
        elif has_changed:
            # Content changed - create new version
            new_version_node = existing_node.create_next_version(
                new_content=new_content.copy(),
                change_event_id=change_event.id if change_event else None,
                change_type=change_type,
                fecha_vigencia=version.fecha_vigencia
            )
            self._register_node(new_version_node)
            
            if change_event:
                change_event.add_affected_node(node_path)
            
            return new_version_node
        else:
            # No changes - return existing node
            return existing_node

    def _mark_removed_nodes(
        self, 
        change_event: ChangeEvent,
        fecha_vigencia: datetime
    ):
        """
        Mark nodes that existed in previous version but not in current version as REMOVED.
        """
        # Find paths that were in previous version but not in current
        removed_paths = self.previous_version_paths - self.current_version_paths
        
        for path in removed_paths:
            node = self._find_node_by_path(path)
            if node:
                # Create removed version
                removed_node = node.create_next_version(
                    new_content=[],
                    change_event_id=change_event.id,
                    change_type=ChangeType.REMOVED,
                    fecha_vigencia=fecha_vigencia
                )
                # Update registry
                self._register_node(removed_node)
                change_event.add_affected_node(path)

    def detect_level(self, text: str) -> Tuple[Optional[int], Optional[NodeType], Optional[str], Optional[str]]:
        """Detect the hierarchical level and type of a text line."""
        for level, node_type, pattern in self.LEVELS:
            match = pattern.match(text)
            if match:
                name = match.group(1)
                extra_text = match.group(2) if match.lastindex and match.lastindex > 1 else None
                return level, node_type, name, extra_text
        return None, None, None, text

    def parse_version(
        self, 
        version: Version, 
        version_index: int,
        change_event: Optional[ChangeEvent] = None
    ) -> Node:
        """
        Parse a single version and integrate it into the tree.
        """
        # Reset current version tracking
        self.current_version_paths = {"root"}
        self.paragraph_counter = 0
        
        for element in version.content:
            if element.element_type == ElementType.BLOCKQUOTE:
                continue
                
            try:
                text = element.content.strip() if element.content else ""
                level, node_type, name, extra_text = self.detect_level(text)

                if name and node_type == NodeType.ARTICULO:
                    name = name.replace(" ", "_")  # normalize spaces in names

                if node_type == NodeType.PARRAFO:
                    self.paragraph_counter += 1
                    name = str(self.paragraph_counter)
                    
                if level is not None:
                    if node_type == NodeType.DISPOSICION:
                        if element.get("class", None) != "disposicion":
                            continue
                    
                    # Pop stack to appropriate level
                    while self.stack and self.stack[-1].level >= level:
                        self.stack.pop()

                    # Create or update node
                    current_node = self._create_or_update_node(
                        parent=self.stack[-1],
                        level=level,
                        node_type=node_type,
                        name=name,
                        content_text=extra_text,
                        version=version,
                        version_index=version_index,
                        change_event=change_event
                    )
                    
                    self.stack.append(current_node)

                else:
                    # Unstructured text - add to current node
                    if self.stack[-1] != self.root and text:
                        current_node = self.stack[-1]
                        current_node.add_text(text)
                        
            except AttributeError as e:
                if isinstance(element.content, dict):
                    class_name = element.content.get("@class", "unknown")
                    if class_name == NoteType.CITATION:
                        print(f"Skipping citation note: {element.content}")
                    else:
                        raise Exception(f"Error processing element: {element.content}. Error: {e}")

        # After parsing, mark any missing nodes as removed (only for non-base versions)
        if change_event and self.previous_version_paths:
            self._mark_removed_nodes(
                change_event=change_event,
                fecha_vigencia=version.fecha_vigencia
            )
        
        # Update previous version paths for next iteration
        self.previous_version_paths = self.current_version_paths.copy()

        return self.root
    
    def parse_versions(self, versions: List[Version]) -> Node:
        """
        Parse multiple versions into the same tree.
        First version creates the base structure, subsequent versions track changes.
        """
        if not versions:
            return self.root
        
        # Sort by fecha_vigencia to process in chronological order
        sorted_versions = sorted(
            versions, 
            key=lambda v: v.fecha_vigencia if v.fecha_vigencia else datetime.min
        )
        
        # Parse first version (base structure)
        print(f"\n{'='*80}")
        print(f"Parsing BASE version: {sorted_versions[0].id_norma}")
        print(f"Fecha vigencia: {sorted_versions[0].fecha_vigencia}")
        print('='*80)
        self.parse_version(sorted_versions[0], version_index=0, change_event=None)
        
        # Parse subsequent versions with change tracking
        for i in range(1, len(sorted_versions)):
            version = sorted_versions[i]
            
            print(f"\nParsing version {i}: {version.id_norma}")
            print(f"Fecha vigencia: {version.fecha_vigencia}")
            
            # Create ChangeEvent for this version
            change_event = self._get_or_create_change_event(
                source_document_id=version.id_norma,
                fecha_vigencia=version.fecha_vigencia,
                description=f"Changes from {version.id_norma}"
            )
            
            # Parse with change tracking
            self.parse_version(version, version_index=i, change_event=change_event)
        
        return self.root

    def print_tree(
        self, 
        node: Node = None, 
        prefix: str = "", 
        is_last: bool = True, 
        show_versions: bool = False,
        show_all_versions: bool = False,
        target_date: Optional[str] = None
    ):
        """Print the tree structure with proper formatting."""
        
        if node is None:
            node = self.root
            header = f'{node.get_full_name()}'
            if show_all_versions:
                header += " [ALL VERSIONS]"
            elif target_date:
                header += f" [AS OF {datetime.fromisoformat(target_date).strftime('%Y-%m-%d')}]"
            print(header)
            
            children = [item for item in node.content if isinstance(item, Node)]
            for i, child in enumerate(children):
                self.print_tree(
                    child, "", i == len(children) - 1, 
                    show_versions, show_all_versions, target_date
                )
            return
        
        # Determine which versions to display
        if show_all_versions:
            versions_to_show = node.get_all_versions()
        elif target_date:
            version_at_date = node.get_version_at_date(node, target_date)
            versions_to_show = [version_at_date] if version_at_date else []
        else:
            versions_to_show = [node]
        
        # Skip if no valid version at target date
        if not versions_to_show or (target_date and not versions_to_show[0]):
            return
        
        # Print each version
        for version_idx, display_node in enumerate(versions_to_show):
            is_last_version = (version_idx == len(versions_to_show) - 1)
            
            # Connector logic
            if show_all_versions and version_idx > 0:
                connector = f"   ╰─ v{display_node.version_index} "
            else:
                connector = "└─ " if is_last else "├─ "
            
            # Version info
            version_info = ""
            if show_versions or show_all_versions:
                parts = [f"v{display_node.version_index}"]
                if display_node.change_type:
                    parts.append(display_node.change_type.value)
                if display_node.fecha_vigencia:
                    vigencia = datetime.fromisoformat(display_node.fecha_vigencia) if isinstance(display_node.fecha_vigencia, str) else display_node.fecha_vigencia
                    parts.append(f"from:{vigencia.strftime('%Y-%m-%d')}")
                if display_node.fecha_caducidad:
                    caducidad = datetime.fromisoformat(display_node.fecha_caducidad) if isinstance(display_node.fecha_caducidad, str) else display_node.fecha_caducidad
                    parts.append(f"to:{caducidad.strftime('%Y-%m-%d')}")
                version_info = f" [{', '.join(parts)}]"
            
            print(f"{prefix}{connector}{display_node.get_full_name()}{version_info}")
            
            # Prefix for children
            if show_all_versions and not is_last_version:
                extension = "   │  " if not is_last else "      "
            else:
                extension = "   " if is_last else "│  "
            
            new_prefix = prefix + extension
            
            # Print children (only for last/current version)
            if is_last_version or not show_all_versions:
                items = display_node.content
                for i, item in enumerate(items):
                    is_last_item = (i == len(items) - 1)
                    
                    if isinstance(item, Node):
                        self.print_tree(
                            item, new_prefix, is_last_item, 
                            show_versions, show_all_versions, target_date
                        )
                    else:
                        text_connector = "└─ " if is_last_item else "├─ "
                        preview = item[:80] + "..." if len(item) > 80 else item
                        print(f'{new_prefix}{text_connector}"{preview}"')

    def get_change_summary(self) -> Dict[str, ChangeEvent]:
        """Get all change events tracked during parsing"""
        return self.change_events
    
    def print_change_summary(self):
        """Print a summary of all changes with before/after content"""
        print(f"\n{'='*80}")
        print(f"CHANGE SUMMARY for {self.target_document_id}")
        print('='*80)
        
        for change_id, change_event in self.change_events.items():
            print(f"\n{change_event}")
            print(f"  Affected nodes ({len(change_event.affected_nodes)}):")
            
            for node_path in sorted(change_event.affected_nodes):
                node = self._find_node_by_path(node_path)
                if node:
                    print(f"\n    [{node.change_type.value if node.change_type else 'N/A'}] {node_path}")
                    print(f"    Version: v{node.version_index}")
                    
                    # Show before/after for changes
                    if node.previous_version:
                        prev_content = self._extract_content_from_node(node.previous_version)
                        curr_content = self._extract_content_from_node(node)
                        
                        if node.change_type == ChangeType.REMOVED:
                            print(f"    BEFORE: {prev_content[:200] if prev_content else '(empty)'}")
                            print(f"    AFTER:  (removed)")
                        elif node.change_type == ChangeType.REPLACED:
                            print(f"    BEFORE: {prev_content[:200] if prev_content else '(empty)'}")
                            print(f"    AFTER:  {curr_content[:200] if curr_content else '(empty)'}")
                        elif node.change_type == ChangeType.ADDED:
                            print(f"    BEFORE: (didn't exist)")
                            print(f"    AFTER:  {curr_content[:200] if curr_content else '(empty)'}")