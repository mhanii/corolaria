# infrastructure/graphdb/neo4j_adapter.py
from typing import List, Dict, Any, Optional
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

    def create_vector_index(self, index_name: str, label: str, property_name: str, dimensions: int, similarity_function: str):
        """
        Create a vector index in Neo4j.
        """
        query = f"""
        CREATE VECTOR INDEX {index_name} IF NOT EXISTS
        FOR (n:{label}) ON (n.{property_name})
        OPTIONS {{indexConfig: {{
          `vector.dimensions`: {dimensions},
          `vector.similarity_function`: '{similarity_function}'
        }}}}
        """
        self.conn.execute_write(query, {})
    
    # ========== Retrieval Methods ==========
    
    def vector_search(self, query_embedding: List[float], top_k: int = 10, 
                     label: str = "Article", index_name: str = "article_embeddings") -> List[Dict[str, Any]]:
        """
        Perform vector similarity search using Neo4j's vector index.
        
        Args:
            query_embedding: The embedding vector to search for
            top_k: Number of results to return
            label: Node label to search (default: Article)
            index_name: Name of the vector index to use
            
        Returns:
            List of dicts containing article data and similarity scores
        """
        query = f"""
        CALL db.index.vector.queryNodes($index_name, $top_k, $query_vector)
        YIELD node, score
        MATCH (node)-[:PART_OF*]->(parent)
        WITH node, score, collect(parent) as hierarchy
        MATCH (node)<-[:HAS_CONTENT|PART_OF*]-(normativa:Normativa)
        RETURN 
            node.id as article_id,
            node.name as article_number,
            node.text as article_text,
            node.embedding as embedding,
            score,
            normativa.titulo as normativa_title,
            normativa.id as normativa_id,
            [h in hierarchy | {{type: labels(h)[0], name: h.name}}] as context_path
        ORDER BY score DESC
        """
        
        # Neo4j's execute_query doesn't support YIELD well, need to use driver session
        with self.conn._driver.session() as session:
            result = session.run(query, {
                "index_name": index_name,
                "top_k": top_k,
                "query_vector": query_embedding
            })
            return [dict(record) for record in result]
    
    def keyword_search(self, keywords: str, top_k: int = 10, 
                      label: str = "Article") -> List[Dict[str, Any]]:
        """
        Perform keyword search on article text and name.
        Uses case-insensitive pattern matching.
        
        Args:
            keywords: Search keywords
            top_k: Number of results to return
            label: Node label to search
            
        Returns:
            List of dicts containing matching articles
        """
        query = f"""
        MATCH (node:{label})
        WHERE toLower(node.text) CONTAINS toLower($keywords) 
           OR toLower(node.name) CONTAINS toLower($keywords)
        MATCH (node)-[:PART_OF*]->(parent)
        WITH node, collect(parent) as hierarchy
        MATCH (node)<-[:HAS_CONTENT|PART_OF*]-(normativa:Normativa)
        RETURN 
            node.id as article_id,
            node.name as article_number,
            node.text as article_text,
            node.embedding as embedding,
            normativa.titulo as normativa_title,
            normativa.id as normativa_id,
            [h in hierarchy | {{type: labels(h)[0], name: h.name}}] as context_path
        LIMIT $top_k
        """
        
        with self.conn._driver.session() as session:
            result = session.run(query, {"keywords": keywords, "top_k": top_k})
            return [dict(record) for record in result]
    
    def get_article_with_context(self, article_id: str, context_window: int = 2) -> Dict[str, Any]:
        """
        Get an article along with surrounding articles (context windowing).
        Fetches N articles before and after the target article.
        
        Args:
            article_id: ID of the target article
            context_window: Number of articles to fetch before/after
            
        Returns:
            Dict with target article and context articles
        """
        query = """
        MATCH (target:Article {id: $article_id})
        MATCH (target)-[:PART_OF*]->(parent)
        WITH target, collect(parent) as hierarchy
        MATCH (target)<-[:HAS_CONTENT|PART_OF*]-(normativa:Normativa)
        
        // Get articles in the same parent structure
        MATCH (sibling:Article)-[:PART_OF]->(commonParent)
        WHERE (target)-[:PART_OF]->(commonParent)
        
        WITH target, normativa, hierarchy, collect(DISTINCT sibling) as siblings
        
        RETURN 
            target.id as article_id,
            target.name as article_number,
            target.text as article_text,
            target.embedding as embedding,
            normativa.titulo as normativa_title,
            normativa.id as normativa_id,
            [h in hierarchy | {type: labels(h)[0], name: h.name}] as context_path,
            [s in siblings | {id: s.id, name: s.name, text: s.text}] as surrounding_articles
        """
        
        with self.conn._driver.session() as session:
            result = session.run(query, {"article_id": article_id})
            record = result.single()
            return dict(record) if record else None
    
    def get_articles_by_structure(self, structure_id: str, 
                                 structure_type: str = "Título") -> List[Dict[str, Any]]:
        """
        Get all articles within a specific structural element (Title, Chapter, Book).
        
        Args:
            structure_id: ID of the structure node
            structure_type: Type of structure (Título, Capítulo, Libro)
            
        Returns:
            List of articles in that structure
        """
        query = f"""
        MATCH (structure:{structure_type} {{id: $structure_id}})
        MATCH (article:Article)-[:PART_OF*]->(structure)
        MATCH (article)<-[:HAS_CONTENT|PART_OF*]-(normativa:Normativa)
        MATCH (article)-[:PART_OF*]->(parent)
        WITH article, normativa, collect(parent) as hierarchy
        RETURN 
            article.id as article_id,
            article.name as article_number,
            article.text as article_text,
            article.embedding as embedding,
            normativa.titulo as normativa_title,
            normativa.id as normativa_id,
            [h in hierarchy | {{type: labels(h)[0], name: h.name}}] as context_path
        ORDER BY article.name
        """
        
        with self.conn._driver.session() as session:
            result = session.run(query, {"structure_id": structure_id})
            return [dict(record) for record in result]
    
    def get_article_versions(self, article_id: str) -> List[Dict[str, Any]]:
        """
        Get all versions of an article (historical versions via NEXT_VERSION relationships).
        
        Args:
            article_id: ID of any version of the article
            
        Returns:
            List of all versions ordered chronologically
        """
        query = """
        MATCH (article:Article {id: $article_id})
        
        // Get all previous versions
        OPTIONAL MATCH path1 = (article)-[:PREVIOUS_VERSION*]->(older)
        WITH article, collect(DISTINCT older) as previous_versions
        
        // Get all next versions
        OPTIONAL MATCH path2 = (article)-[:NEXT_VERSION*]->(newer)
        WITH article, previous_versions, collect(DISTINCT newer) as next_versions
        
        // Combine all versions
        WITH previous_versions + [article] + next_versions as all_versions
        UNWIND all_versions as version
        
        MATCH (version)<-[:HAS_CONTENT|PART_OF*]-(normativa:Normativa)
        MATCH (version)-[:PART_OF*]->(parent)
        WITH version, normativa, collect(parent) as hierarchy
        
        RETURN 
            version.id as article_id,
            version.name as article_number,
            version.text as article_text,
            version.fecha_vigencia as validity_start,
            version.fecha_caducidad as validity_end,
            normativa.titulo as normativa_title,
            normativa.id as normativa_id,
            [h in hierarchy | {type: labels(h)[0], name: h.name}] as context_path
        ORDER BY version.fecha_vigencia
        """
        
        with self.conn._driver.session() as session:
            result = session.run(query, {"article_id": article_id})
            return [dict(record) for record in result]
    
    def get_articles_by_subject(self, materia_id: str) -> List[Dict[str, Any]]:
        """
        Get all articles related to a specific subject matter (Materia).
        
        Args:
            materia_id: ID of the Materia node
            
        Returns:
            List of articles about that subject
        """
        query = """
        MATCH (materia:Materia {id: $materia_id})
        MATCH (normativa:Normativa)-[:ABOUT]->(materia)
        MATCH (normativa)-[:HAS_CONTENT]->(content)
        MATCH (article:Article)-[:PART_OF*]->(content)
        MATCH (article)-[:PART_OF*]->(parent)
        WITH article, normativa, collect(parent) as hierarchy
        RETURN 
            article.id as article_id,
            article.name as article_number,
            article.text as article_text,
            article.embedding as embedding,
            normativa.titulo as normativa_title,
            normativa.id as normativa_id,
            [h in hierarchy | {type: labels(h)[0], name: h.name}] as context_path
        ORDER BY normativa.titulo, article.name
        """
        
        with self.conn._driver.session() as session:
            result = session.run(query, {"materia_id": materia_id})
            return [dict(record) for record in result]
