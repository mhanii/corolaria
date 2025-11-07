from typing import List, Optional, Union,Dict, Tuple
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
from src.domain.models.common.node import Node, NodeType, StructureNode, ArticleNode,ArticleElementNode
from .change_handler import ChangeHandler
from .node_factory.factory import NodeFactory
from src.domain.models.common.base import ElementType, NoteType
from src.domain.models.normativa import Version
from .utils.print_tree import print_tree
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
        self.change_handler = ChangeHandler(self.target_document_id)

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
                    # = OLD =
                    # extra_text in case of a paragraph is None. However, it is very important in case of APARTADOS
                    # we assign text to extra_text for compatibility 
                    
                    # = New = (only the comment changed lol)
                    if self.stack[-1].node_type != NodeType.ARTICULO and self.stack[-1].node_type != NodeType.PARRAFO:

                        level, node_type, name, extra_text = None, None, None, text
                    else:
                        self.paragraph_counter += 1
                        name = self.paragraph_counter
                        extra_text = text # To continue the loop without having to write another if specifically for the paragraph

                    
                if level is not None:
                    # if  node_type == NodeType.DISPOSICION: # confirm it is a disposicion
                    #     if element.get("class", None) != "disposicion": # this in reality doens' work because element won't have a class
                    #         continue
                    while self.stack and self.stack[-1].level >= level:
                        self.stack.pop()

                    current_node = self.node_factory.create_node(
                        parent=self.stack[-1],
                        level=level,
                        node_type=node_type,
                        name=name,
                        content= [],
                    )
                    self.stack.append(current_node)

                    if extra_text:
                        current_node.add_text(extra_text)
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
            key=lambda v: v.fecha_vigencia if v.fecha_vigencia else '18000101'
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

                self.change_handler.diff_versions(node_new, node_old)
            node_old = node_new
        



        return self.root

    

    