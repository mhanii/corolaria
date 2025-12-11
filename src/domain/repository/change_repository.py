# domain/repository/change_repository.py
from typing import List, Dict, Any
from src.domain.interfaces.graph_adapter import GraphAdapter
from src.domain.services.change_handler import ChangeEvent, AffectedNode


class ChangeRepository:
    """
    Repository for persisting change events to Neo4j.
    
    Schema:
    - SourceNormativa -[:INTRODUCED_CHANGE]-> ChangeEvent
    - ChangeEvent -[:MODIFIES]-> TargetNormativa  
    - ChangeEvent -[:CHANGED {type: "added"|"modified"|"removed"}]-> Article
    """
    
    def __init__(self, adapter: GraphAdapter):
        self.adapter = adapter
    
    def save_change_event(self, change_event: ChangeEvent, normativa_id: str = None) -> dict:
        """
        Save a change event to Neo4j with all relationships.
        
        Creates:
        1. ChangeEvent node
        2. SourceNormativa -[:INTRODUCED_CHANGE]-> ChangeEvent
        3. ChangeEvent -[:MODIFIES]-> TargetNormativa
        4. ChangeEvent -[:CHANGED {type}]-> Article (for each affected article)
        """
        # ChangeEvent properties
        props = {
            "id": change_event.id,
            "target_document_id": change_event.target_document_id,
            "source_document_id": change_event.source_document_id,
            "description": change_event.description or "",
            "affected_nodes_count": len(change_event.affected_nodes),
        }
        
        # Merge the ChangeEvent node
        result = self.adapter.merge_node(["ChangeEvent"], props)
        
        if not result:
            return {"success": False, "id": None, "articles_linked": 0}
        
        event_id = result["id"]
        
        # 1. ChangeEvent -[:MODIFIES]-> TargetNormativa
        if normativa_id:
            self.adapter.merge_relationship(
                from_id=event_id,
                to_id=normativa_id,
                rel_type="MODIFIES",
                from_label="ChangeEvent",
                to_label="Normativa"
            )
        
        # 2. SourceNormativa -[:INTRODUCED_CHANGE]-> ChangeEvent
        if change_event.source_document_id:
            self.adapter.merge_relationship(
                from_id=change_event.source_document_id,
                to_id=event_id,
                rel_type="INTRODUCED_CHANGE",
                from_label="Normativa",
                to_label="ChangeEvent"
            )
        
        # 3. ChangeEvent -[:CHANGED {type}]-> Article (for each affected article)
        # Deduplicate by article_id and collect change types
        article_changes = {}  # article_id -> set of change types
        for affected in change_event.affected_nodes:
            if affected.node_id:
                if affected.node_id not in article_changes:
                    article_changes[affected.node_id] = set()
                article_changes[affected.node_id].add(affected.change_type)
        
        # Create relationships for each unique article
        articles_linked = 0
        for article_id, change_types in article_changes.items():
            # Use the most significant change type: removed > modified > added
            if "removed" in change_types:
                change_type = "removed"
            elif "modified" in change_types:
                change_type = "modified"
            else:
                change_type = "added"
            
            self.adapter.merge_relationship(
                from_id=event_id,
                to_id=article_id,
                rel_type="CHANGED",
                properties={"type": change_type},
                from_label="ChangeEvent",
                to_label="articulo"
            )
            articles_linked += 1
        
        return {"success": True, "id": event_id, "articles_linked": articles_linked}

    
    def save_change_events(self, change_events: Dict[str, ChangeEvent], normativa_id: str) -> dict:
        """Save multiple change events for a normativa."""
        saved_count = 0
        total_articles_linked = 0
        # Iterate over a copy to prevent "dictionary changed size during iteration"
        for event in list(change_events.values()):
            result = self.save_change_event(event, normativa_id)
            if result.get("success"):
                saved_count += 1
                total_articles_linked += result.get("articles_linked", 0)
        
        return {"events_saved": saved_count, "articles_linked": total_articles_linked}
    
    def find_changes_for_document(self, normativa_id: str) -> List[Dict[str, Any]]:
        """Find all change events that modified a specific document."""
        query = """
        MATCH (event:ChangeEvent)-[:MODIFIES]->(n:Normativa {id: $normativa_id})
        OPTIONAL MATCH (event)-[r:CHANGED]->(article)
        RETURN event.id as id, 
               event.source_document_id as source,
               event.affected_nodes_count as affected_count,
               collect({article_id: article.id, change_type: r.type}) as changes
        ORDER BY event.source_document_id
        """
        
        with self.adapter.conn._driver.session() as session:
            result = session.run(query, {"normativa_id": normativa_id})
            return [dict(record) for record in result]