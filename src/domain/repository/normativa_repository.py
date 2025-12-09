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
    
    def save_normativa(self, normativa: NormativaCons) -> dict:
        """
        Save complete normativa document.
        
        Returns:
            Dict with save statistics: {
                doc_id, nodes_created, relationships_created,
                materias_count, normativa_title
            }
        """
        # Track counts
        nodes_created = 0
        relationships_created = 0
        
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
        nodes_created += 1  # Normativa node

        # Create and connect Materia nodes
        materias_count = 0
        for materia in normativa.analysis.materias:
            materia_props = {"id": materia.id, "name": materia.get_name()}
            materia_node = self.adapter.merge_node(["Materia"], materia_props)
            if materia_node:
                self.adapter.merge_relationship(from_id=doc_id, to_id=materia_node["id"], rel_type="ABOUT")
                nodes_created += 1
                relationships_created += 1
                materias_count += 1

        # Create and connect Departamento node
        departamento = normativa.metadata.departamento
        departamento_props = {"id": departamento.id, "name": departamento.get_name()}
        departamento_node = self.adapter.merge_node(["Departamento"], departamento_props)
        if departamento_node:
            self.adapter.merge_relationship(from_id=doc_id, to_id=departamento_node["id"], rel_type="ISSUED_BY")
            nodes_created += 1
            relationships_created += 1

        # Create and connect Rango node
        rango = normativa.metadata.rango
        rango_props = {"id": rango.id, "name": rango.get_name()}
        rango_node = self.adapter.merge_node(["Rango"], rango_props)
        if rango_node:
            self.adapter.merge_relationship(from_id=doc_id, to_id=rango_node["id"], rel_type="HAS_RANK")
            nodes_created += 1
            relationships_created += 1

        # Save content tree and get its counts
        tree_result = self.save_content_tree(normativa.content_tree, normativa_id=doc_id)
        nodes_created += tree_result.get("nodes_count", 0)
        relationships_created += tree_result.get("relationships_count", 0)

        return {
            "doc_id": doc_id,
            "normativa_title": normativa.metadata.titulo,
            "nodes_created": nodes_created,
            "relationships_created": relationships_created,
            "materias_count": materias_count,
            "tree_nodes": tree_result.get("nodes_count", 0),
            "tree_relationships": tree_result.get("relationships_count", 0)
        }
    
    def delete_normativa(self, normativa_id: str) -> dict:
        """
        Delete a normativa and its content tree, preserving shared nodes.
        
        This method is used for rollback operations. It deletes:
        - All nodes connected to the Normativa via PART_OF (content tree)
        - The Normativa node itself
        
        It preserves:
        - Materia, Departamento, Rango nodes (shared between normativas)
        - Only the relationships TO these shared nodes are removed
        
        Args:
            normativa_id: The ID of the Normativa to delete
            
        Returns:
            Dict with deletion statistics: {nodes_deleted, relationships_removed}
        """
        result = {"nodes_deleted": 0, "relationships_removed": 0}
        
        # Step 1: Delete all nodes in the content tree
        # These are nodes that have PART_OF paths leading to the Normativa
        delete_tree_query = """
        MATCH (n)-[:PART_OF*]->(normativa:Normativa {id: $normativa_id})
        WITH n
        DETACH DELETE n
        RETURN count(n) as deleted_count
        """
        
        tree_result = self.adapter.conn.execute_write(
            delete_tree_query,
            {"normativa_id": normativa_id}
        )
        if tree_result:
            result["nodes_deleted"] += tree_result.get("deleted_count", 0)
        
        # Step 2: Delete the Normativa node itself
        # DETACH DELETE removes all relationships (ABOUT, ISSUED_BY, HAS_RANK)
        # but does NOT delete the connected shared nodes
        delete_normativa_query = """
        MATCH (normativa:Normativa {id: $normativa_id})
        DETACH DELETE normativa
        RETURN count(normativa) as deleted_count
        """
        
        normativa_result = self.adapter.conn.execute_write(
            delete_normativa_query,
            {"normativa_id": normativa_id}
        )
        if normativa_result:
            result["nodes_deleted"] += normativa_result.get("deleted_count", 0)
        
        return result
    
    

    def save_content_tree(self, node: Node, normativa_id: str = None) -> dict:
        """
        Save the entire content tree using batch operations for performance.
        Preserves all ArticleNode metadata (introduced_by, fecha_vigencia, fecha_caducidad).
        
        Returns:
            Dict with id and counts: {id, nodes_count, relationships_count}
        """
        if isinstance(node, str):
            return {"id": None, "nodes_count": 0, "relationships_count": 0}
        
        # Collect all nodes and relationships in a single traversal
        nodes_data = []
        relationships_data = []
        self._collect_tree_data(node, nodes_data, relationships_data, normativa_id)
        
        # Batch persist: nodes first, then relationships
        self.adapter.batch_merge_nodes(nodes_data)
        self.adapter.batch_merge_relationships(relationships_data)
        
        return {
            "id": node.id,
            "nodes_count": len(nodes_data),
            "relationships_count": len(relationships_data)
        }
    
    def _collect_tree_data(self, node: Node, nodes_data: list, relationships_data: list, normativa_id: str = None):
        """
        Recursively collect node and relationship data for batch persistence.
        
        Skips structural nodes (libro, titulo, capitulo, seccion, subseccion) to reduce
        database size. Articles link directly to Normativa, and the `path` property 
        preserves hierarchy info for display.
        """
        if isinstance(node, str):
            return
        
        # Structural nodes to skip (don't create graph nodes, but traverse children)
        STRUCTURAL_TYPES = {NodeType.LIBRO, NodeType.TITULO, NodeType.CAPITULO, 
                           NodeType.SECCION, NodeType.SUBSECCION}
        
        is_structural = node.node_type in STRUCTURAL_TYPES
        is_root = node.node_type == NodeType.ROOT
        
        # Build node properties (skip for ROOT and structural nodes)
        if not is_root and not is_structural:
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
            
            # Skip creating relationships for structural children
            child_is_structural = child.node_type in STRUCTURAL_TYPES
            if child_is_structural:
                continue
            
            # Database Relationship Logic
            if is_root or is_structural:
                # Children of ROOT or structural nodes link directly to Normativa
                if normativa_id:
                    relationships_data.append({
                        "from_id": child.id,
                        "to_id": normativa_id,
                        "rel_type": "PART_OF",
                        "props": {}
                    })
            else:
                # Non-structural nodes (articles) link children to themselves
                relationships_data.append({
                    "from_id": child.id,
                    "to_id": node.id,
                    "rel_type": "PART_OF",
                    "props": {}
                })
        
        # Add ArticleNode version relationships
        if isinstance(node, ArticleNode):
            # Note: INTRODUCED_BY relationship removed - change events capture this info
            # The introduced_by property is still stored on the node for queryability
            
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