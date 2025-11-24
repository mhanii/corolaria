# domain/repository/normativa_repository.py
from typing import Optional, List
from src.domain.models.normativa import NormativaCons, Version
from src.domain.models.common.node import Node, NodeType, ArticleNode,ArticleElementNode
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

        content_tree_root = self.save_content_tree(normativa.content_tree)
        if content_tree_root:
            self.adapter.merge_relationship(
                from_id=doc_id,
                to_id=content_tree_root["id"],
                rel_type="HAS_CONTENT"
            )

        return doc_id
    
    

    def save_content_tree(self, node: Node):
        if isinstance(node, str):
            return -1
        
        doc_props = {"id": node.id, "name": node.name,"text":node.text}
        
        if isinstance(node, ArticleNode) and node.embedding:
            doc_props["embedding"] = node.embedding

        parent_node = self.adapter.merge_node([node.node_type], doc_props)

        for item in node.content:
            child_node = self.save_content_tree(item)
            if child_node != -1 and child_node is not None:
                self.adapter.merge_relationship(
                    from_id=child_node["id"],
                    to_id=parent_node["id"],
                    rel_type="PART_OF"
                )

                if isinstance(node,ArticleNode):
                    if node.previous_version:
                        self.adapter.merge_relationship(
                            from_id=node.previous_version.id,
                            to_id=node.id,
                            rel_type="NEXT_VERSION"
                        )

                        self.adapter.merge_relationship(
                            from_id=node.id,
                            to_id=node.previous_version.id,
                            rel_type="PREVIOUS_VERSION"
                        )

        return parent_node