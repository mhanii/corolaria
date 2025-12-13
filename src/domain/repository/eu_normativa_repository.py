# domain/repository/eu_normativa_repository.py
"""
Repository for EU legal documents (EUR-Lex).

Uses unified Normativa label with source differentiation.
"""
from typing import Optional, List, Dict
from src.domain.models.eu_normativa import EUNormativa, EUDocumentType
from src.domain.models.common.node import Node, NodeType, ArticleNode, ArticleElementNode
from src.domain.interfaces.graph_adapter import GraphAdapter
from src.domain.services.article_text_builder import ArticleTextBuilder
from src.utils.spanish_number_converter import normalize_article_number


class EUNormativaRepository:
    """
    High-level domain operations for EU legal documents.
    
    Uses unified 'Normativa' label with source="EUR-Lex" property
    to enable cross-source queries while maintaining type distinction.
    """
    
    def __init__(self, adapter: GraphAdapter):
        self.adapter = adapter
        self.text_builder = ArticleTextBuilder()
    
    def save_normativa(self, normativa: EUNormativa) -> dict:
        """
        Save complete EU document.
        
        Returns:
            Dict with save statistics: {
                doc_id, nodes_created, relationships_created,
                normativa_title
            }
        """
        # Track counts
        nodes_created = 0
        relationships_created = 0
        
        # Create main document node with unified Normativa label + EU properties
        doc_props = {
            "id": normativa.id,
            "titulo": normativa.metadata.title,
            "source": "EUR-Lex",  # Distinguish from BOE
            
            # EU-specific identifiers
            "celex": normativa.metadata.celex_number,
            "cellar_id": normativa.metadata.cellar_id,
            "eli_uri": normativa.metadata.eli_uri,
            
            # Document type
            "document_type": normativa.metadata.document_type.value if normativa.metadata.document_type else None,
            "author": normativa.metadata.author.value if normativa.metadata.author else None,
            
            # Dates
            "fecha_publicacion": normativa.metadata.date_publication.isoformat() if normativa.metadata.date_publication else None,
            "fecha_disposicion": normativa.metadata.date_document.isoformat() if normativa.metadata.date_document else None,
            "fecha_vigencia": normativa.metadata.date_entry_into_force.isoformat() if normativa.metadata.date_entry_into_force else None,
            
            # Publication
            "oj_reference": normativa.metadata.oj_reference,
            "oj_series": normativa.metadata.oj_series,
            
            # Status
            "estatus_consolidacion": "consolidated" if normativa.metadata.is_consolidated else "original",
            "status": normativa.metadata.status.value if normativa.metadata.status else None,
            
            # URLs
            "url_eurlex": normativa.metadata.url_eurlex,
            "url_cellar": normativa.metadata.url_cellar,
        }
        
        # Use unified Normativa label for cross-source queries
        doc_node = self.adapter.merge_node(["Normativa"], doc_props)
        doc_id = doc_node["id"] if doc_node else normativa.id
        nodes_created += 1
        
        # Create EuroVoc subject term nodes (similar to Materia)
        eurovoc_count = 0
        for term in normativa.metadata.eurovoc_descriptors:
            term_props = {"id": f"eurovoc:{term}", "name": term}
            term_node = self.adapter.merge_node(["TerminoEuroVoc"], term_props)
            if term_node:
                self.adapter.merge_relationship(
                    from_id=doc_id, to_id=term_node["id"], rel_type="ABOUT",
                    from_label="Normativa", to_label="TerminoEuroVoc"
                )
                nodes_created += 1
                relationships_created += 1
                eurovoc_count += 1
        
        # Create document type node (like Rango)
        if normativa.metadata.document_type:
            type_props = {
                "id": f"eu_type:{normativa.metadata.document_type.value}",
                "name": normativa.metadata.document_type.name
            }
            type_node = self.adapter.merge_node(["TipoDocumentoUE"], type_props)
            if type_node:
                self.adapter.merge_relationship(
                    from_id=doc_id, to_id=type_node["id"], rel_type="HAS_TYPE",
                    from_label="Normativa", to_label="TipoDocumentoUE"
                )
                nodes_created += 1
                relationships_created += 1
        
        # Create institution node (like Departamento)
        if normativa.metadata.author:
            inst_props = {
                "id": f"eu_institution:{normativa.metadata.author.value}",
                "name": normativa.metadata.author.name
            }
            inst_node = self.adapter.merge_node(["InstitucionUE"], inst_props)
            if inst_node:
                self.adapter.merge_relationship(
                    from_id=doc_id, to_id=inst_node["id"], rel_type="ISSUED_BY",
                    from_label="Normativa", to_label="InstitucionUE"
                )
                nodes_created += 1
                relationships_created += 1
        
        # Save content tree
        tree_result = self.save_content_tree(normativa.content_tree, normativa_id=doc_id)
        nodes_created += tree_result.get("nodes_count", 0)
        relationships_created += tree_result.get("relationships_count", 0)
        
        return {
            "doc_id": doc_id,
            "normativa_title": normativa.metadata.title,
            "nodes_created": nodes_created,
            "relationships_created": relationships_created,
            "eurovoc_count": eurovoc_count,
            "tree_nodes": tree_result.get("nodes_count", 0),
            "tree_relationships": tree_result.get("relationships_count", 0)
        }
    
    def save_content_tree(self, node: Node, normativa_id: str = None) -> dict:
        """
        Save the entire content tree using batch operations.
        
        Returns:
            Dict with id and counts: {id, nodes_count, relationships_count}
        """
        if isinstance(node, str):
            return {"id": None, "nodes_count": 0, "relationships_count": 0}
        
        # Collect all nodes and relationships
        nodes_data = []
        relationships_data = []
        self._collect_tree_data(node, nodes_data, relationships_data, normativa_id)
        
        # Batch persist
        self.adapter.batch_merge_nodes(nodes_data)
        self.adapter.batch_merge_relationships(relationships_data)
        
        return {
            "id": node.id,
            "nodes_count": len(nodes_data),
            "relationships_count": len(relationships_data)
        }
    
    def _normalize_article_number(self, name: str) -> Optional[str]:
        """Extract normalized article number from name."""
        return normalize_article_number(name)
    
    def _collect_tree_data(
        self, 
        node: Node, 
        nodes_data: list, 
        relationships_data: list, 
        normativa_id: str = None,
        parent_id: str = None,
        path: str = ""
    ):
        """
        Recursively collect node and relationship data for batch persistence.
        
        Only persists ArticleNode and ArticleElementNode to reduce DB size.
        """
        if isinstance(node, str):
            return
        
        current_path = f"{path}/{node.name}" if path else node.name
        node_type = node.node_type.value if hasattr(node.node_type, 'value') else str(node.node_type)
        
        # Skip structural nodes (only persist articles)
        skip_types = {'root', 'libro', 'titulo', 'capitulo', 'seccion', 'subseccion'}
        should_skip = node_type in skip_types
        
        if not should_skip:
            props = {
                "id": node.id,
                "name": node.name,
            }
            
            # Handle ArticleNode - use node_type enum directly as label (produces "articulo")
            if isinstance(node, ArticleNode):
                # Build full article text using ArticleTextBuilder
                props["full_text"] = self.text_builder.build_full_text(node)
                props["path"] = current_path
                
                # Clean article number for O(1) lookups
                clean_num = self._normalize_article_number(node.name)
                if clean_num:
                    props["clean_number"] = clean_num
                
                # Include embedding if present
                if hasattr(node, 'embedding') and node.embedding is not None:
                    props["embedding"] = node.embedding
            
            # Handle ArticleElementNode
            elif isinstance(node, ArticleElementNode):
                props["text"] = node.text or ""
            
            # Generic node
            else:
                if hasattr(node, 'text'):
                    props["text"] = node.text or ""
            
            # Use node.node_type enum directly as label (same as BOE repository)
            nodes_data.append({"labels": [node.node_type], "props": props})
            
            # Create PART_OF relationship to Normativa
            if normativa_id:
                relationships_data.append({
                    "from_id": node.id,
                    "to_id": normativa_id,
                    "rel_type": "PART_OF",
                    "from_label": node.node_type,
                    "to_label": "Normativa",
                    "props": {}
                })
        
        # Recurse through children
        if hasattr(node, 'content') and node.content:
            for child in node.content:
                if isinstance(child, Node):
                    self._collect_tree_data(
                        child, nodes_data, relationships_data,
                        normativa_id=normativa_id,
                        parent_id=node.id if not should_skip else parent_id,
                        path=current_path if not should_skip else path
                    )
    
    def delete_normativa(self, normativa_id: str) -> dict:
        """
        Delete EU normativa and its content tree.
        
        Returns:
            Dict with deletion statistics
        """
        query = """
        MATCH (n:Normativa {id: $normativa_id})
        OPTIONAL MATCH (content)-[:PART_OF]->(n)
        DETACH DELETE content, n
        RETURN count(content) as nodes_deleted
        """
        
        result = self.adapter.run_write(query, {"normativa_id": normativa_id})
        return {"nodes_deleted": result[0]["nodes_deleted"] if result else 0}
