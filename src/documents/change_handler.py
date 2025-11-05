from dataclasses import dataclass, field
import hashlib
from typing import Optional, List
from .node_factory.base import ArticleNode, ArticleElementNode, Node
from datetime import datetime
from .utils.print_tree import print_tree
import logging

output_logger = logging.getLogger("output_logger")

@dataclass
class ChangeEvent:
    """Represents all changes made to ONE document by ONE legislative act"""
    id: str  
    
    # The document being changed
    target_document_id: str
    
    # The document making the change
    source_document_id: str
    
    
    description: Optional[str] = None
    
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
        description: Optional[str] = None
    ) -> 'ChangeEvent':
        """Factory method to create a ChangeEvent with proper ID"""
        change_id = cls.generate_id(target_document_id, source_document_id)
        return cls(
            id=change_id,
            target_document_id=target_document_id,
            source_document_id=source_document_id,
            description=description
        )
    
    def add_affected_node(self, node_path: str):
        """Add a node that was affected by this change"""
        if node_path not in self.affected_nodes:
            self.affected_nodes.append(node_path)
    
    def print_summary(self, verbose: bool = False):
        """
        Imprime un resumen en lenguaje natural de este evento de cambio.
        Ideal para inspección humana o indexación semántica (RAG).
        """
        output_logger.info("\n" + "="*80)
        output_logger.info(f"📜 Resumen del Evento de Cambio: {self.id}")
        output_logger.info(f"🗂 Documento afectado (destino): {self.target_document_id}")
        output_logger.info(f"🪶 Documento origen del cambio: {self.source_document_id}")
        if self.description:
            output_logger.info(f"📝 Descripción: {self.description}")
        output_logger.info(f"🧩 Nodos afectados: {len(self.affected_nodes)}")

        if verbose and self.affected_nodes:
            output_logger.info("\nDetalle de los nodos afectados:")
            for node_path in self.affected_nodes:
                partes = node_path.split('/')
                indent = "  " * (len(partes) - 1)
                output_logger.info(f"{indent}- {node_path}")

        output_logger.info("="*80 + "\n")

        # También devolver texto para uso en embeddings o RAG
        return (
            f"El evento de cambio {self.id} modifica {len(self.affected_nodes)} nodos "
            f"en el documento {self.target_document_id} como resultado de {self.source_document_id}. "
            + (f"Descripción: {self.description}. " if self.description else "")
            + ("Nodos afectados: " + ", ".join(self.affected_nodes[:10]) + "..."
               if len(self.affected_nodes) > 10 else 
               "Nodos afectados: " + ", ".join(self.affected_nodes))
        )
    
    def __repr__(self):
        return (f"ChangeEvent(id={self.id[:12]}..., "
                f"target={self.target_document_id}, "
                f"source={self.source_document_id}, "
                f"affects={len(self.affected_nodes)} nodes)")

class ChangeHandler:
    def __init__(self, document):
        self.change_events = {}
        self.target_document = document 

    def _create_or_get_change_event(self, source_document: str):
        change_id = ChangeEvent.generate_id(
            source_doc_id=source_document, 
            target_doc_id=self.target_document
        )
        if change_id not in self.change_events:
            self.change_events[change_id] = ChangeEvent.create(
                target_document_id=self.target_document,
                source_document_id=source_document
            )
        return self.change_events[change_id]

    def diff_versions(self, new: ArticleNode, old: ArticleNode):
        output_logger.info(f"\n\n{'^'*32}[ Comparing two nodes ]{'^'*32}\n")
        output_logger.info(f"{'='*40}[ NEW ]{'='*40}")
        print_tree(node=new)
        output_logger.info(f"{'='*40}[ OLD ]{'='*40}")
        print_tree(node=old)

        new.previous_version = old
        old.next_version = new

        # Deduplicate ArticleElementNodes first
        self._merge_duplicate_elements(new, old)

        # Detect what changed between versions
        source_doc = new.introduced_by or "unknown"
        change_event = self._create_or_get_change_event(source_doc)
        self._detect_changes(old, new, change_event)

        output_logger.info(f"\nDetected {len(change_event.affected_nodes)} affected nodes for {change_event.id}\n")

    # ------------------------------------------------------------------------
    # Deduplication (same as before)
    # ------------------------------------------------------------------------
    def _merge_duplicate_elements(self, new_article: ArticleNode, old_article: ArticleNode):
        old_registry = {}
        self._build_element_registry(old_article, old_registry)
        self._replace_duplicates(new_article, old_registry)

        output_logger.info(f"\n{'='*40}[ AFTER MERGE ]{'='*40}")
        output_logger.info(f"Deduplicated {len([n for n in old_registry.values() if n.other_parents])} element nodes")

    def _build_element_registry(self, node: Node, registry: dict):
        if isinstance(node, ArticleElementNode):
            node_hash = node.compute_hash()
            registry[node_hash] = node
        for item in node.content:
            if isinstance(item, Node):
                self._build_element_registry(item, registry)

    def _replace_duplicates(self, node: Node, old_registry: dict):
        if not hasattr(node, 'content') or not node.content:
            return
        new_content = []
        for item in node.content:
            if isinstance(item, ArticleElementNode):
                item_hash = item.compute_hash()
                if item_hash in old_registry:
                    old_node = old_registry[item_hash]
                    old_node.merge_with(item)
                    new_content.append(old_node)
                    output_logger.info(f"  ✓ Merged: {item.node_type} {item.name}")
                else:
                    new_content.append(item)
                    output_logger.info(f"  ✗ New/Changed: {item.node_type} {item.name}")
                    self._replace_duplicates(item, old_registry)
            elif isinstance(item, Node):
                new_content.append(item)
                self._replace_duplicates(item, old_registry)
            else:
                new_content.append(item)
        node.content = new_content

    # ------------------------------------------------------------------------
    # New Section: Change Detection
    # ------------------------------------------------------------------------
    def _detect_changes(self, old: Node, new: Node, change_event: ChangeEvent, path: str = ""):
        """
        Recursively detect differences between old and new nodes.
        Records added, removed, and modified nodes.
        """
        current_path = f"{path}/{new.node_type}:{new.name}" if path else f"{new.node_type}:{new.name}"

        # Case 1 — New node didn't exist before
        if not old:
            change_event.add_affected_node(current_path)
            output_logger.info(f"🟢 Added: {current_path}")
            return

        # Case 2 — Node type or name changed
        if old.node_type != new.node_type or old.name != new.name:
            change_event.add_affected_node(current_path)
            output_logger.info(f"🟡 Modified structure: {current_path}")

        # Case 3 — Compare content (only for element nodes)
        if isinstance(new, ArticleElementNode):
            old_texts = [t.strip() for t in old.content if isinstance(t, str)]
            new_texts = [t.strip() for t in new.content if isinstance(t, str)]
            if old_texts != new_texts:
                change_event.add_affected_node(current_path)
                output_logger.info(f"🟠 Text changed in {current_path}")

        # Case 4 — Recurse into children
        old_children = [c for c in old.content if isinstance(c, Node)]
        new_children = [c for c in new.content if isinstance(c, Node)]

        for n_child in new_children:
            o_child = next((c for c in old_children if c.name == n_child.name and c.node_type == n_child.node_type), None)
            self._detect_changes(o_child, n_child, change_event, path=current_path)

        # Case 5 — Removed nodes
        for o_child in old_children:
            if not any(c.name == o_child.name and c.node_type == o_child.node_type for c in new_children):
                removed_path = f"{current_path}/{o_child.node_type}:{o_child.name}"
                change_event.add_affected_node(removed_path)
                output_logger.info(f"🔴 Removed: {removed_path}")

    def print_summary(self, verbose: bool = False):
        """
        Imprime un resumen general de todos los eventos de cambio detectados 
        para el documento destino.
        """
        output_logger.info("\n" + "#"*90)
        output_logger.info(f"📘 Resumen de Cambios del Documento Destino: {self.target_document}")
        output_logger.info("#"*90)

        if not self.change_events:
            output_logger.info("No se han detectado ni registrado cambios aún.\n")
            return

        for change_id, event in self.change_events.items():
            output_logger.info(f"\n🔹 Evento {change_id[:12]}:")
            output_logger.info(f"   ↳ Documento origen: {event.source_document_id}")
            output_logger.info(f"   ↳ Nodos afectados: {len(event.affected_nodes)}")
            if event.description:
                output_logger.info(f"   ↳ Descripción: {event.description}")

            if verbose:
                for node in event.affected_nodes:
                    output_logger.info(f"     - {node}")

        output_logger.info("\n" + "#"*90 + "\n")

        # Devuelve un texto combinado en lenguaje natural para embeddings o RAG
        resumen_combinado = "\n".join([
            f"[Cambio {e.id}] Afecta {len(e.affected_nodes)} nodos. "
            f"Origen: {e.source_document_id}. "
            f"Destino: {e.target_document_id}. "
            + (f"Descripción: {e.description}. " if e.description else "")
            + "Nodos: " + ", ".join(e.affected_nodes[:10]) + 
              ("..." if len(e.affected_nodes) > 10 else "")
            for e in self.change_events.values()
        ])
        return resumen_combinado
