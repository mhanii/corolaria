from typing import List, Optional, Union,Dict, Tuple
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
from .node_factory.base import Node, NodeType, StructureNode, ArticleNode,ArticleElementNode
from .node_factory.factory import NodeFactory
from .base import ElementType, NoteType
from .normativa_cons import Version
import re



class TreeBuilder:
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
        (8, NodeType.APARTADO_ALFA, re.compile(r'^([a-z])\)\s+(.+)', re.I)),
        (8, NodeType.ORDINAL_ALFA, re.compile(r'^(\d+\.+ª)\s*(.*)$', re.I)),
        (10, NodeType.ORDINAL_NUMERICO, re.compile(r'^(\d+\.+º)\s*(.*)$', re.I)),
        (9, NodeType.PARRAFO, re.compile(r'^\s*(.+)')), # Should always be last because it matches con everything
    ]

    def __init__(self, target_document_id: str):
        self.target_document_id = target_document_id
        self.root = Node(
            name="Content", 
            level=-1, 
            node_type=NodeType.ROOT, 
            id=0,
            path="root"
        )

        self.stack = [self.root]
        self.node_factory = NodeFactory()

    def detect_level(self, text: str) -> Tuple[Optional[int], Optional[NodeType], Optional[str], Optional[str]]:
        """Detect the hierarchical level and type of a text line."""
        for level, node_type, pattern in self.LEVELS:
            match = pattern.match(text)
            if match:
                name = match.group(1)
                extra_text = match.group(2) if match.lastindex and match.lastindex > 1 else None
                return level, node_type, name, extra_text
        return None, None, None, text
        

    def diff_versions(self, new: ArticleNode, old: ArticleNode):
        print(f"\n\n{"^"*32}[ Comparing two nodes ]{"^"*32}\n")
        print(f"{"="*40}[ NEW ]{"="*40}")  
        self.print_tree(new)

        print(f"{"="*40}[ OLD ]{"="*40}") 
        self.print_tree(old)

        # Link article versions
        new.previous_version = old
        old.next_version = new
        
        # Deduplicate ArticleElementNodes
        self._merge_duplicate_elements(new, old)


    def _merge_duplicate_elements(self, new_article: ArticleNode, old_article: ArticleNode):
        """
        Compare ArticleElementNodes between two article versions and merge duplicates.
        Unchanged nodes in new_article will be replaced with references to old_article nodes.
        """
        # Build hash registry from old article
        old_registry = {}
        self._build_element_registry(old_article, old_registry)
        
        # Process new article and merge duplicates
        self._replace_duplicates(new_article, old_registry)
        
        print(f"\n{"="*40}[ AFTER MERGE ]{"="*40}")
        print(f"Deduplicated {len([n for n in old_registry.values() if n.other_parents])} element nodes")


    def _build_element_registry(self, node: Node, registry: dict):
        """Recursively build a hash registry of all ArticleElementNodes"""
        if isinstance(node, ArticleElementNode):
            node_hash = node.compute_hash()
            registry[node_hash] = node
        
        # Recurse into child nodes
        for item in node.content:
            if isinstance(item, Node):
                self._build_element_registry(item, registry)


    def _replace_duplicates(self, node: Node, old_registry: dict):
        """
        Recursively find and replace duplicate ArticleElementNodes.
        If a node in the new tree matches one in old_registry, replace it.
        """
        if not hasattr(node, 'content') or not node.content:
            return
        
        new_content = []
        
        for item in node.content:
            if isinstance(item, ArticleElementNode):
                item_hash = item.compute_hash()
                
                # Check if this element already exists in old version
                if item_hash in old_registry:
                    # Found duplicate! Use the old node instead
                    old_node = old_registry[item_hash]
                    old_node.merge_with(item)  # Track the new parent
                    new_content.append(old_node)  # Replace with old node reference
                    print(f"  ✓ Merged: {item.node_type} {item.name}")
                else:
                    # This is a new/changed element
                    new_content.append(item)
                    print(f"  ✗ New/Changed: {item.node_type} {item.name}")
                    # Still recurse in case it has children
                    self._replace_duplicates(item, old_registry)
            elif isinstance(item, Node):
                # Other node types - just recurse
                new_content.append(item)
                self._replace_duplicates(item, old_registry)
            else:
                # Plain text
                new_content.append(item)
        
        # Replace the content list
        node.content = new_content


        

    def parse_version(
        self, 
        version: Version, 
    ) -> Node:
        """
        Parse a single version and integrate it into the tree.
        If this is not the first version, changes are tracked via.
        """
        
        self.paragraph_counter = 0 


        element = version.content[0]
        text = element.content.strip() if element.content else ""
        level, node_type, name, extra_text = self.detect_level(text)

        block_level = level # The block type is set by the first element in it.
        block_type = node_type # we could get it from the node but just to save complexity

        for element in version.content:
            if element.element_type == ElementType.BLOCKQUOTE:
                continue
                
            try:
                text = element.content.strip() if element.content else ""
                level, node_type, name, extra_text = self.detect_level(text)

                if name:
                   name = name.replace(" ","_") # normalize spaces in names

                if node_type == NodeType.PARRAFO:

                    # extra_text in case of a paragraph is None. However, it is very important in case of APARTADOS
                    # we assign text to extra_text for compatibility 
                    
                    if self.stack[-1].node_type != NodeType.ARTICULO:

                        level, node_type, name, extra_text = None, None, None, text
                    else:
                        self.paragraph_counter += 1
                        name = self.paragraph_counter
                        extra_text = text # To continue the loop without having to write another if specifically for the paragraph

                    
                if level is not None:
                    if  node_type == NodeType.DISPOSICION: # confirm it is a disposicion
                        if element.get("class", None) != "disposicion": # this in reality doens' work because element won't have a class
                            continue
                    while self.stack and self.stack[-1].level >= level:
                        self.stack.pop()

                    current_node = self.node_factory.create_node(
                        parent=self.stack[-1],
                        level=level,
                        node_type=node_type,
                        name=name,
                        content=[extra_text] if extra_text else [],
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
                    else :
                        raise Exception(f"Error processing element: {element.content}. Error: {e}")

            
        while self.stack and self.stack[-1].level > block_level:
            self.stack.pop()  

        return block_type, self.stack[-1]
    
    def parse_versions(self, versions: List[Version]) -> Node:
        """
        Parse multiple versions into the same tree.
        First version creates the base structure, subsequent versions track changes.
        """
        if not versions:
            return self.root
        
        sorted_versions = sorted(
            versions, 
            key=lambda v: v.fecha_vigencia if v.fecha_vigencia else datetime.min
        )
        
        node_type, node_old = self.parse_version(sorted_versions[0])
        if(isinstance(node_old,ArticleNode)):
            node_old.introduced_by = sorted_versions[0].id_norma
            node_old.fecha_vigencia = sorted_versions[0].fecha_vigencia
        # Parse subsequent versions with change tracking
        for i in range(1, len(sorted_versions)):
            node_type, node_new = self.parse_version(sorted_versions[i])
            if(isinstance(node_new,ArticleNode)):
                node_new.introduced_by = sorted_versions[i].id_norma
                node_new.fecha_vigencia = sorted_versions[i].fecha_vigencia
                node_old.fecha_caducidad = node_new.fecha_vigencia

                self.diff_versions(node_new,node_old)
            node_old = node_new
        
        return self.root

    def print_tree(
            self, 
            node: Node = None, 
            prefix: str = "", 
            is_last: bool = True, 
            target_date: Optional[str] = None
        ):
        """Print the tree structure with proper formatting."""
        
        if node is None:
            node = self.root
            header = f'{node.get_full_name()}'

            if target_date:
                header += f" [AS OF {datetime.fromisoformat(target_date).strftime('%Y-%m-%d')}]"
            print(header)
            
            children = [item for item in node.content if isinstance(item, Node)]
            for i, child in enumerate(children):
                self.print_tree(
                    child, "", i == len(children) - 1, 
                )
            return
    
        connector = "└─ " if is_last else "├─ "
        extension = "   " if is_last else "│  "   

        new_prefix = prefix + extension    
        print(f"{prefix}{connector}{node.get_full_name()}")
        
        items = node.content
        for i, item in enumerate(items):
            is_last_item = (i == len(items) - 1)
            
            if isinstance(item, Node):
                self.print_tree(
                    item, new_prefix, is_last_item, 
                    target_date
                )
            else:
                text_connector = "└─ " if is_last_item else "├─ "
                preview = item[:80] + "..." if len(item) > 80 else item
                print(f'{new_prefix}{text_connector}"{preview}"')