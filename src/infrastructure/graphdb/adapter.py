
# infrastructure/graphdb/neo4j_adapter.py
from .connection import Neo4jConnection
class Neo4jAdapter:
    """Low-level Neo4j operations"""
    
    def __init__(self, connection: Neo4jConnection):
        self.conn = connection
    

    # # We will comment this to keep all creation inside merge
    # def create_node(self, labels: list, properties: dict) -> str:
    #     """Create a node and return its ID"""
    #     labels_str = ":".join(labels)
    #     query = f"""
    #     CREATE (n:{labels_str} $props)
    #     RETURN elementId(n) as id
    #     """
    #     result = self.conn.execute_write(query, {"props": properties})
    #     return result.single()["id"]
    

    def merge_node(self, labels, properties):
        label_string = ":".join(labels)
        query = f"""
        MERGE (n:{label_string} {{id: $props.id}})
        SET n += $props
        RETURN n.id AS id
        """
        record = self.conn.execute_write(query, {"props": properties})
        return {"id": record["id"]} if record else None
        
    def merge_relationship(self, from_id: str, to_id: str, 
                          rel_type: str, properties: dict = None):
        """Merge relationship between nodes"""
        if properties:
            # Build Cypher literal map string, e.g. "{k1: $props.k1, k2: $props.k2}"
            props_str = "{" + ", ".join([f"{k}: $props.{k}" for k in properties.keys()]) + "}"
        else:
            props_str = "{}"

        query = f"""
        MATCH (a {{id: $from_id}})
        MATCH (b {{id: $to_id}})
        MERGE (a)-[r:{rel_type} {props_str}]->(b)
        RETURN r
        """
        return self.conn.execute_write(query, {
            "from_id": from_id,
            "to_id": to_id,
            "props": properties or {}
        })
    
