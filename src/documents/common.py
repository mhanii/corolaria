from typing import List, Optional, Union
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
from .normativa_cons import Version, Node
import re
from .base import ElementType, NodeType, ChangeType
from .normativa_cons import Element, Node, ChangeEvent
from typing import Dict, Tuple
import difflib






class TreeBuilder:
    LEVELS = [
        (0, NodeType.LIBRO, re.compile(r'^LIBRO\s+(.+)', re.I)),
        (1, NodeType.TITULO, re.compile(r'^TÍTULO\s+(.+)', re.I)),
        (2, NodeType.CAPITULO, re.compile(r'^CAPÍTULO\s+(.+)', re.I)),
        (3, NodeType.SECCION, re.compile(r'^Sección\s+(\d+\.ª)(?:\s*\.?\s*(.*))?', re.I)),
        (4, NodeType.SUBSECCION, re.compile(r'^Subsección\s+(\d+ª)(?:\s*\.?\s*(.*))?', re.I)),
        (5, NodeType.ARTICULO_UNICO, re.compile(r'^Artículo\s+único(?:\s*\.?\s*(.*))?', re.I)),
        (5, NodeType.ARTICULO, re.compile(r'^Artículo\s+(\d+)')),
        (6, NodeType.APARTADO_NUMERICO, re.compile(r'^(\d+)\.\s+(.+)')),
        (7, NodeType.PARRAFO, re.compile(r'^\.\s+(.+)')),
        (8, NodeType.APARTADO_ALFA, re.compile(r'^([a-z])\)\s+(.+)', re.I)),
        (8, NodeType.ORDINAL, re.compile(r'^(\d+ª)\s*(.*)$')),
    ]

    def __init__(self, target_document_id: str):
        self.target_document_id = target_document_id
        self.root = Node(
            name="Content", 
            level=-1, 
            node_type=NodeType.ROOT, 
            id=0,
            version_number=0,
            path="root"
        )
        self.stack = [self.root]
        
        # Key: node_path -> Latest version of that node
        self.node_registry: Dict[str, Node] = {"root": self.root}
        
        # Key: change_event_id -> ChangeEvent
        self.change_events: Dict[str, ChangeEvent] = {}
        
        # Counter for unique node IDs
        self.next_node_id = 1

    def detect_level(self, text: str) -> Tuple[Optional[int], Optional[NodeType], Optional[str], Optional[str]]:
        """Detect the hierarchical level and type of a text line."""
        for level, node_type, pattern in self.LEVELS:
            match = pattern.match(text)
            if match:
                name = match.group(1)
                extra_text = match.group(2) if match.lastindex and match.lastindex > 1 else None
                return level, node_type, name, extra_text
        return None, None, None, None

    def _get_node_path(self, node: Node) -> str:
        """Generate unique path for a node (e.g., 'TITULO_I/CAPITULO_II/Articulo_5')"""
        if node.path:
            return node.path
            
        path_parts = []
        current = node
        while current and current.node_type != NodeType.ROOT:
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
        Returns the current version of the node.
        """
        # Build the path for this node
        temp_node = Node(
            id=-1,
            name=name,
            level=level,
            node_type=node_type,
            parent=parent,
            version_number=0,
            path=""
        )
        node_path = self._get_node_path(temp_node)
        
        # Check if node already exists
        existing_node = self._find_node_by_path(node_path)
        
        # Prepare new content
        new_content = [content_text] if content_text else []
        
        # Compare content
        has_changed, change_type = self._compare_node_content(existing_node, new_content)
        
        if existing_node is None:
            # Brand new node - create original version
            new_node = Node(
                id=self.next_node_id,
                name=name,
                level=level,
                node_type=node_type,
                content=new_content.copy(),
                parent=parent,
                version_number=0,
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
            
            # Update parent's content to point to new version
            parent_content = parent.content
            try:
                old_index = parent_content.index(existing_node)
                parent_content[old_index] = new_version_node
            except ValueError:
                parent.add_child(new_version_node)
            
            # Update registry
            self._register_node(new_version_node)
            
            if change_event:
                change_event.add_affected_node(node_path)
            
            return new_version_node
        else:
            # No change - return existing node
            return existing_node

    def parse_version(
        self, 
        version: Version, 
        version_index: int,
        change_event: Optional[ChangeEvent] = None
    ) -> Node:
        """
        Parse a single version and integrate it into the tree.
        If this is not the first version, changes are tracked via ChangeEvent.
        """
        # Reset stack to root for each version
        self.stack = [self.root]
        
        for element in version.content:
            if element.element_type == ElementType.BLOCKQUOTE:
                continue
                
            text = element.content.strip() if element.content else ""
            level, node_type, name, extra_text = self.detect_level(text)

            if level is not None:
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
                    
                    # Check if adding this text would constitute a change
                    old_content = self._extract_content_from_node(current_node)
                    new_content = old_content + [text]
                    
                    has_changed, change_type = self._compare_node_content(
                        current_node, 
                        new_content
                    )
                    
                    if has_changed and change_event:
                        # Create new version with added text
                        new_version = current_node.create_next_version(
                            new_content=new_content,
                            change_event_id=change_event.id,
                            change_type=change_type,
                            fecha_vigencia=version.fecha_vigencia
                        )
                        
                        # Update parent reference
                        parent = current_node.parent
                        if parent:
                            try:
                                idx = parent.content.index(current_node)
                                parent.content[idx] = new_version
                            except ValueError:
                                pass
                        
                        self._register_node(new_version)
                        change_event.add_affected_node(new_version.path)
                        
                        # Update stack
                        self.stack[-1] = new_version
                    else:
                        # Just add text to current node
                        current_node.add_text(text)
            
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
        
        # Parse first version (base structure, no ChangeEvent)
        # print(f"\n{'='*80}")
        # print(f"Parsing BASE version: {sorted_versions[0].id_norma}")
        # print(f"Fecha vigencia: {sorted_versions[0].fecha_vigencia}")
        # print('='*80)
        self.parse_version(sorted_versions[0], version_index=0, change_event=None)
        
        # Parse subsequent versions with change tracking
        for i in range(1, len(sorted_versions)):
            version = sorted_versions[i]
            
            print(f"\n{'='*80}")
            print(f"Parsing version {i}: {version.id_norma}")
            print(f"Fecha vigencia: {version.fecha_vigencia}")
            print('='*80)
            
            # Create ChangeEvent for this version
            change_event = self._get_or_create_change_event(
                source_document_id=version.id_norma,
                fecha_vigencia=version.fecha_vigencia,
                description=f"Changes from {version.id_norma}"
            )
            
            # Parse with change tracking
            self.parse_version(version, version_index=i, change_event=change_event)
            
            print(f"ChangeEvent {change_event.id[:12]}... affected {len(change_event.affected_nodes)} nodes")
            for node_path in change_event.affected_nodes:
                node = self._find_node_by_path(node_path)
                if node:
                    print(f"  - {node_path}: {node.change_type}")
        
        return self.root

    def print_tree(
        self, 
        node: Node = None, 
        prefix: str = "", 
        is_last: bool = True, 
        show_versions: bool = False,
        show_all_versions: bool = False,
        target_date: Optional[datetime] = None
    ):
        """
        Print the tree structure with proper box-drawing characters.
        
        Args:
            node: Starting node (None = root)
            prefix: Prefix for tree drawing
            is_last: Whether this is the last child
            show_versions: Show version metadata for current version
            show_all_versions: Show ALL historical versions of each node
            target_date: Show tree state at specific date (ignored if show_all_versions=True)
        """
        if node is None:
            node = self.root
            header = f'{node.get_full_name()}'
            if show_all_versions:
                header += " [SHOWING ALL VERSIONS]"
            elif target_date:
                header += f" [AS OF {target_date.strftime('%Y-%m-%d')}]"
            print(header)
            
            children = [item for item in node.content if isinstance(item, Node)]
            for i, child in enumerate(children):
                self.print_tree(
                    child, "", i == len(children) - 1, 
                    show_versions, show_all_versions, target_date
                )
            return
        
        # Determine which version(s) to display
        if show_all_versions:
            versions_to_show = node.get_all_versions()
        elif target_date:
            versions_to_show = [node.get_version_at_date(target_date)]
        else:
            versions_to_show = [node]
        
        # Print each version
        for version_idx, display_node in enumerate(versions_to_show):
            is_last_version = (version_idx == len(versions_to_show) - 1)
            
            # Adjust connector for multiple versions
            if show_all_versions and len(versions_to_show) > 1:
                if version_idx == 0:
                    connector = "└─ " if is_last else "├─ "
                else:
                    # Subsequent versions use a special connector
                    connector = "   ╰─ v" + str(display_node.version_number) + " "
            else:
                connector = "└─ " if is_last else "├─ "
            
            # Build version info
            version_info = ""
            if show_versions or show_all_versions:
                version_info = f" [v{display_node.version_number}"
                if display_node.change_type:
                    version_info += f", {display_node.change_type.value}"
                if display_node.fecha_vigencia:
                    vigencia_str = display_node.fecha_vigencia.strftime('%Y-%m-%d') if isinstance(display_node.fecha_vigencia, datetime) else str(display_node.fecha_vigencia)
                    version_info += f", since: {vigencia_str}"
                if display_node.fecha_caducidad:
                    caducidad_str = display_node.fecha_caducidad.strftime('%Y-%m-%d') if isinstance(display_node.fecha_caducidad, datetime) else str(display_node.fecha_caducidad)
                    version_info += f", until: {caducidad_str}"
                version_info += "]"
            
            print(f"{prefix}{connector}{display_node.get_full_name()}{version_info}")
            
            # Prepare prefix for children and content
            if show_all_versions and not is_last_version:
                # More versions coming, use special prefix
                extension = "   │  " if not is_last else "      "
            else:
                extension = "   " if is_last else "│  "
            
            new_prefix = prefix + extension
            
            # Print content for this version
            items = display_node.content
            for i, item in enumerate(items):
                is_last_item = (i == len(items) - 1)
                
                if isinstance(item, Node):
                    # Only recurse for children if this is the last/only version shown
                    if show_all_versions:
                        if is_last_version:
                            self.print_tree(
                                item, new_prefix, is_last_item, 
                                show_versions, show_all_versions, target_date
                            )
                    else:
                        self.print_tree(
                            item, new_prefix, is_last_item, 
                            show_versions, show_all_versions, target_date
                        )
                else:
                    text_connector = "└─ " if is_last_item else "├─ "
                    preview = item[:100] + "..." if len(item) > 100 else item
                    print(f'{new_prefix}{text_connector}"{preview}"')

    def get_change_summary(self) -> Dict[str, ChangeEvent]:
        """Get all change events tracked during parsing"""
        return self.change_events
    
    def print_change_summary(self):
        """Print a summary of all changes"""
        print(f"\n{'='*80}")
        print(f"CHANGE SUMMARY for {self.target_document_id}")
        print('='*80)
        
        for change_id, change_event in self.change_events.items():
            print(f"\n{change_event}")
            print(f"  Affected nodes:")
            for node_path in change_event.affected_nodes:
                node = self._find_node_by_path(node_path)
                if node:
                    print(f"    - {node_path}")
                    print(f"      Type: {node.change_type.value if node.change_type else 'N/A'}")
                    print(f"      Version: {node.version_number}")
