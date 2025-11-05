
# domain/repository/tree_repository.py

from src.domain.models.common.node import ArticleNode, Node, NodeType
from src.infrastructure.graphdb.adapter import Neo4jAdapter


class TreeRepository:
    """Repository for hierarchical tree structures"""
    
    def __init__(self, adapter: Neo4jAdapter):
        self.adapter = adapter
    
    def save_tree(self, root: Node, version_id: str):
        """Save entire node tree to graph"""
        node_id = self._save_node_recursive(root, version_id)
        return node_id
    
    def _save_node_recursive(self, node: Node, version_id: str, parent_id: str = None) -> str:
        """Recursively save node and children"""
        # Determine node labels based on type
        labels = ["Node"]
        if isinstance(node, ArticleNode):
            labels.append("Article")
        elif node.node_type in (NodeType.LIBRO, NodeType.TITULO, NodeType.CAPITULO):
            labels.append("Structure")
        
        # Prepare properties
        props = {
            "node_id": node.id,
            "name": node.name,
            "level": node.level,
            "node_type": node.node_type.value,
            "path": node.get_hierarchy_string(),
        }
        
        # Add article-specific properties
        if isinstance(node, ArticleNode):
            props.update({
                "fecha_vigencia": node.fecha_vigencia,
                "fecha_caducidad": node.fecha_caducidad,
                "introduced_by": node.introduced_by,
            })
        
        # Create node
        node_id = self.adapter.create_node(labels, props)
        
        # Link to version
        self.adapter.create_relationship(version_id, node_id, "HAS_NODE")
        
        # Link to parent if exists
        if parent_id:
            self.adapter.create_relationship(parent_id, node_id, "HAS_CHILD", 
                                           {"order": len(node.parent.content) if node.parent else 0})
        
        # Save text content
        text_items = [item for item in node.content if isinstance(item, str)]
        if text_items:
            text_props = {"content": "\n".join(text_items)}
            text_id = self.adapter.create_node(["TextContent"], text_props)
            self.adapter.create_relationship(node_id, text_id, "HAS_CONTENT")
        
        # Recursively save children
        child_nodes = [item for item in node.content if isinstance(item, Node)]
        for child in child_nodes:
            self._save_node_recursive(child, version_id, node_id)
        
        return node_id
    
    def load_tree(self, version_id: str) -> Node:
        """Load entire tree structure for a version"""
        query = """
        MATCH (v:Version)-[:HAS_NODE]->(root:Node)
        WHERE elementId(v) = $version_id AND NOT (root)<-[:HAS_CHILD]-()
        CALL apoc.path.subgraphAll(root, {
            relationshipFilter: "HAS_CHILD>"
        })
        YIELD nodes, relationships
        RETURN nodes, relationships
        """
        
        result = self.adapter.conn.execute_query(query, {"version_id": version_id})
        
        # TODO: Reconstruct tree from graph data
        return None


