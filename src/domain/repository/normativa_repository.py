# domain/repository/normativa_repository.py
from typing import Optional, List
from src.domain.models.normativa import NormativaCons, Version
from src.domain.models.common.node import Node, NodeType, ArticleNode, ArticleElementNode
from src.infrastructure.graphdb.adapter import Neo4jAdapter
from src.domain.services.article_text_builder import ArticleTextBuilder

class NormativaRepository:
    """High-level domain operations for legal documents"""
    
    def __init__(self, adapter: Neo4jAdapter):
        self.adapter = adapter
        self.text_builder = ArticleTextBuilder()
    
    def save_normativa(self, normativa: NormativaCons) -> str:
        """Save complete normativa document"""
        # Create main document node
        doc_props = { 
            "id": normativa.id,
            "titulo": normativa.metadata.titulo,
            "fecha_publicacion": normativa.metadata.fecha_publicacion,
            "fecha_disposicion": normativa.metadata.fecha_disposicion,
            "fecha_vigencia": normativa.metadata.fecha_vigencia,
            "fecha_actualizacion": normativa.metadata.fecha_actualizacion,
            "url_eli": normativa.metadata.url_eli,
            "url_html_consolidado": normativa.metadata.url_html_consolidado,
            "estatus_derogacion": normativa.metadata.estatus_derogacion,
            "estatus_anulacion": normativa.metadata.estatus_anulacion,
            "vigencia_agotada": normativa.metadata.vigencia_agotada,
            "estado_consolidacion": normativa.metadata.estado_consolidacion.get_name(),
            "diario": normativa.metadata.diario,
            "diario_numero": normativa.metadata.diario_numero,
            "ambito": normativa.metadata.ambito.get_name(),
        }
        
        doc_node = self.adapter.merge_node(["Normativa"], doc_props)
        doc_id = doc_node["id"] if doc_node else normativa.id

        # Create and connect Materia nodes
        for materia in normativa.analysis.materias:
            materia_props = {"id": materia.id, "name": materia.get_name()}
            materia_node = self.adapter.merge_node(["Materia"], materia_props)
            if materia_node:
                self.adapter.merge_relationship(from_id=doc_id, to_id=materia_node["id"], rel_type="ABOUT")

        # Create and connect Departamento node
        departamento = normativa.metadata.departamento
        departamento_props = {"id": departamento.id, "name": departamento.get_name()}
        departamento_node = self.adapter.merge_node(["Departamento"], departamento_props)
        if departamento_node:
            self.adapter.merge_relationship(from_id=doc_id, to_id=departamento_node["id"], rel_type="ISSUED_BY")

        # Create and connect Rango node
        rango = normativa.metadata.rango
        rango_props = {"id": rango.id, "name": rango.get_name()}
        rango_node = self.adapter.merge_node(["Rango"], rango_props)
        if rango_node:
            self.adapter.merge_relationship(from_id=doc_id, to_id=rango_node["id"], rel_type="HAS_RANK")

        content_tree_root = self.save_content_tree(normativa.content_tree, normativa_id=doc_id)
        if content_tree_root:
            self.adapter.merge_relationship(
                from_id=doc_id,
                to_id=content_tree_root["id"],
                rel_type="HAS_CONTENT"
            )

        return doc_id
    
    

    def save_content_tree(self, node: Node, normativa_id: str = None):
        """
        Save the entire content tree using batch operations for performance.
        Preserves all ArticleNode metadata (introduced_by, fecha_vigencia, fecha_caducidad).
        """
        if isinstance(node, str):
            return None
        
        # Collect all nodes and relationships in a single traversal
        nodes_data = []
        relationships_data = []
        self._collect_tree_data(node, nodes_data, relationships_data, normativa_id)
        
        # Batch persist: nodes first, then relationships
        self.adapter.batch_merge_nodes(nodes_data)
        self.adapter.batch_merge_relationships(relationships_data)
        
        return {"id": node.id}
    
    def _collect_tree_data(self, node: Node, nodes_data: list, relationships_data: list, normativa_id: str = None):
        """
        Recursively collect node and relationship data for batch persistence.
        """
        if isinstance(node, str):
            return
        
        # Build node properties
        props = {
            "id": node.id,
            "name": node.name,
            "text": node.text
        }
        
        # Add ArticleNode-specific metadata
        if isinstance(node, ArticleNode):
            if node.embedding:
                props["embedding"] = node.embedding
            if node.introduced_by:
                props["introduced_by"] = node.introduced_by
            if node.fecha_vigencia:
                props["fecha_vigencia"] = node.fecha_vigencia
            if node.fecha_caducidad:
                props["fecha_caducidad"] = node.fecha_caducidad
            # Pre-compute full text for efficient retrieval (no N+1 queries)
            props["full_text"] = self.text_builder.build_full_text(node)
            # Store hierarchy path for context display
            props["path"] = node.path or self.text_builder.build_hierarchy_path(node)
        
        # Add to nodes batch
        nodes_data.append({
            "labels": [node.node_type],
            "props": props
        })
        
        # Process children
        for item in node.content:
            if isinstance(item, str):
                continue
                
            child = item
            self._collect_tree_data(child, nodes_data, relationships_data, normativa_id)
            
            # PART_OF relationship
            relationships_data.append({
                "from_id": child.id,
                "to_id": node.id,
                "rel_type": "PART_OF",
                "props": {}
            })
        
        # Add ArticleNode version relationships
        if isinstance(node, ArticleNode):
            # INTRODUCED_BY relationship for queryability
            if node.introduced_by and normativa_id:
                relationships_data.append({
                    "from_id": node.id,
                    "to_id": node.introduced_by,  # Link to introducing Normativa
                    "rel_type": "INTRODUCED_BY",
                    "props": {}
                })
            
            # Version chain relationships
            if node.previous_version:
                relationships_data.append({
                    "from_id": node.previous_version.id,
                    "to_id": node.id,
                    "rel_type": "NEXT_VERSION",
                    "props": {}
                })
                relationships_data.append({
                    "from_id": node.id,
                    "to_id": node.previous_version.id,
                    "rel_type": "PREVIOUS_VERSION",
                    "props": {}
                })