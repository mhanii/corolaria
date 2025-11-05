# domain/repository/normativa_repository.py
from typing import Optional, List
from src.domain.models.normativa import NormativaCons, Version
from src.domain.models.common.node import Node, NodeType, ArticleNode
from src.infrastructure.graphdb.adapter import Neo4jAdapter

class NormativaRepository:
    """High-level domain operations for legal documents"""
    
    def __init__(self, adapter: Neo4jAdapter):
        self.adapter = adapter
    
    def save_normativa(self, normativa: NormativaCons) -> str:
        """Save complete normativa document"""
        # Create main document node
        doc_props = {
            "id": normativa.id,
            "titulo": normativa.metadata.titulo,
            "fecha_publicacion": normativa.metadata.fecha_publicacion,
            "rango": normativa.metadata.rango.get_name(),
            "url_eli": normativa.metadata.url_eli,
            "estatus_derogacion": normativa.metadata.estatus_derogacion,
        }
        
        doc_id = self.adapter.merge_node(["Normativa"], doc_props)
        
        self.save_content_tree(normativa.content_tree)

        return doc_id
    

    def save_content_tree(self, node: Node):
        if isinstance(node, str):
            return -1
        
        doc_props = {"id": node.id, "name": node.name,"text":node.text}
        parent_node = self.adapter.merge_node([node.node_type], doc_props)

        for item in node.content:
            child_node = self.save_content_tree(item)
            if child_node != -1 and child_node is not None:
                self.adapter.merge_relationship(
                    from_id=child_node["id"],
                    to_id=parent_node["id"],
                    rel_type="PART_OF"
                )

        return parent_node