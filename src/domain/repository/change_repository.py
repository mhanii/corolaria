# domain/repository/change_repository.py
from typing import List
from src.infrastructure.graphdb.adapter import Neo4jAdapter

class ChangeRepository:
    """Repository for tracking changes between versions"""

    def __init__(self, adapter: Neo4jAdapter):
        self.adapter = adapter

    def save_change_event(self, change_event) -> str:
        """Save a change event"""
        props = {
            "id": change_event.id,
            "target_document_id": change_event.target_document_id,
            "source_document_id": change_event.source_document_id,
            "description": change_event.description,
            "affected_nodes_count": len(change_event.affected_nodes),
        }

        change_id = self.adapter.create_node(["ChangeEvent"], props)

        # Link to source and target documents
        source_results = self.adapter.find_nodes(
            ["Normativa"],
            {"id": change_event.source_document_id}
        )
        target_results = self.adapter.find_nodes(
            ["Normativa"],
            {"id": change_event.target_document_id}
        )

        if source_results:
            self.adapter.create_relationship(source_results[0]["id"], change_id, "CAUSED_CHANGE")

        if target_results:
            self.adapter.create_relationship(change_id, target_results[0]["id"], "AFFECTS")

        # Save affected nodes
        for node_path in change_event.affected_nodes:
            self._link_affected_node(change_id, node_path)

        return change_id

    def _link_affected_node(self, change_id: str, node_path: str):
        """Link change event to affected nodes"""
        query = """
        MATCH (n:Node {path: $node_path})
        MATCH (c:ChangeEvent)
        WHERE elementId(c) = $change_id
        CREATE (c)-[:AFFECTED_NODE]->(n)
        """

        self.adapter.conn.execute_write(query, {
            "change_id": change_id,
            "node_path": node_path
        })

    def find_changes_affecting_node(self, node_path: str) -> List:
        """Find all changes that affected a specific node"""
        query = """
        MATCH (c:ChangeEvent)-[:AFFECTED_NODE]->(n:Node {path: $node_path})
        RETURN c, c.source_document_id as source
        ORDER BY c.date
        """

        return self.adapter.conn.execute_query(query, {"node_path": node_path})