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

    # ========== Generic Query Methods ==========
    
    def run_query(self, query: str, parameters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Execute a read query and return all results as a list of dictionaries.
        
        Args:
            query: Cypher query string
            parameters: Optional query parameters
            
        Returns:
            List of record dictionaries
        """
        with self.conn._driver.session(database="neo4j") as session:
            result = session.run(query, parameters or {})
            return [dict(record) for record in result]
    
    def run_query_single(self, query: str, parameters: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """
        Execute a read query and return a single result.
        
        Args:
            query: Cypher query string
            parameters: Optional query parameters
            
        Returns:
            Single record dictionary or None
        """
        with self.conn._driver.session(database="neo4j") as session:
            result = session.run(query, parameters or {})
            record = result.single()
            return dict(record) if record else None
    
    def run_write(self, query: str, parameters: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """
        Execute a write query and return the single result.
        
        Args:
            query: Cypher query string
            parameters: Optional query parameters
            
        Returns:
            Single record dictionary or None
        """
        with self.conn._driver.session(database="neo4j") as session:
            result = session.run(query, parameters or {})
            record = result.single()
            return dict(record) if record else None

    # ========== Batch Operations ==========
    
    def batch_merge_nodes(self, nodes_data: list) -> None:
        """
        Create/merge multiple nodes using APOC for optimal performance.
        Supports dynamic labels via apoc.merge.node.
        
        Args:
            nodes_data: List of dicts with 'labels' (list of str) and 'props' (dict)
                       Example: [{"labels": ["articulo"], "props": {"id": 1, "name": "Art 1", ...}}]
        """
        if not nodes_data:
            return
        
        # APOC merge.node: dynamic labels, merge on id, set all properties
        query = """
        UNWIND $batch AS row
        CALL apoc.merge.node(row.labels, {id: row.props.id}, row.props) YIELD node
        RETURN count(node) as count
        """
        self.conn.execute_batch(query, nodes_data)
    
    def batch_merge_relationships(self, relationships_data: list) -> None:
        """
        Create/merge multiple relationships using APOC for optimal performance.
        Supports dynamic relationship types via apoc.merge.relationship.
        
        Args:
            relationships_data: List of dicts with 'from_id', 'to_id', 'rel_type', 'props' (optional)
        """
        if not relationships_data:
            return
        
        # APOC merge.relationship: dynamic rel type with merge semantics
        query = """
        UNWIND $batch AS row
        MATCH (a {id: row.from_id})
        MATCH (b {id: row.to_id})
        CALL apoc.merge.relationship(a, row.rel_type, {}, row.props, b) YIELD rel
        RETURN count(rel) as count
        """
        self.conn.execute_batch(query, relationships_data)

    
    # ========== Retrieval Methods ==========
    
    def vector_search(self, query_embedding: List[float], top_k: int = 10, 
                     label: str = "articulo", index_name: str = "article_embeddings") -> List[Dict[str, Any]]:
        """
        Perform vector similarity search using Neo4j's vector index.
        
        Args:
            query_embedding: The embedding vector to search for
            top_k: Number of results to return
            label: Node label to search (default: articulo)
            index_name: Name of the vector index to use
            
        Returns:
            List of dicts containing article data, similarity scores, dates, and version IDs.
            Article text is pre-computed (stored as full_text), no N+1 queries needed.
        """
        # Optimized single-query approach:
        # - Uses pre-computed node.path instead of dynamic hierarchy traversal
        # - Uses WITH DISTINCT to avoid row explosion from multiple paths
        # - Collects normativa info to handle multiple matches gracefully
        query = f"""
            CALL db.index.vector.queryNodes($index_name, $top_k, $query_vector)
            YIELD node, score
            
            // Use bounded traversal to find normativa, collect to avoid row explosion
            OPTIONAL MATCH (node)-[:PART_OF*1..10]->(normativa:Normativa)
            WITH DISTINCT node, score, head(collect(normativa)) as normativa
            
            // Version relationships (direct, efficient)
            OPTIONAL MATCH (node)<-[:NEXT_VERSION]-(prev_version)
            OPTIONAL MATCH (node)-[:NEXT_VERSION]->(next_version)
            
            RETURN 
                node.id as article_id,
                node.name as article_number,
                node.full_text as article_text,
                node.path as article_path,
                node.fecha_vigencia as fecha_vigencia,
                node.fecha_caducidad as fecha_caducidad,
                normativa.fecha_publicacion as fecha_publicacion,
                prev_version.id as previous_version_id,
                next_version.id as next_version_id,
                score,
                normativa.titulo as normativa_title,
                normativa.id as normativa_id
            ORDER BY score DESC
        """
        
        results = []
        with self.conn._driver.session() as session:
            result = session.run(query, {
                "index_name": index_name,
                "top_k": top_k,
                "query_vector": query_embedding
            })
            for record in result:
                results.append(dict(record))
                    
        return results
    
    def keyword_search(self, keywords: str, top_k: int = 10, 
                      label: str = "articulo") -> List[Dict[str, Any]]:
        """
        Perform keyword search on article text and name.
        Uses case-insensitive pattern matching.
        
        Args:
            keywords: Search keywords
            top_k: Number of results to return
            label: Node label to search
            
        Returns:
            List of dicts containing matching articles with pre-computed full_text
        """
        query = f"""
        MATCH (node:{label})
        WHERE toLower(node.full_text) CONTAINS toLower($keywords) 
           OR toLower(node.name) CONTAINS toLower($keywords)
        MATCH (node)-[:PART_OF*]->(parent)
        WITH node, collect(parent) as hierarchy
        MATCH (node)-[:PART_OF*]->(normativa:Normativa)
        RETURN 
            node.id as article_id,
            node.name as article_number,
            node.full_text as article_text,
            node.path as article_path,
            node.embedding as embedding,
            normativa.titulo as normativa_title,
            normativa.id as normativa_id,
            [h in hierarchy | {{type: labels(h)[0], name: h.name}}] as context_path
        LIMIT $top_k
        """
        
        with self.conn._driver.session() as session:
            result = session.run(query, {"keywords": keywords, "top_k": top_k})
            return [dict(record) for record in result]
    
    def get_article_with_context(self, article_id: str, context_window: int = 2) -> Optional[Dict[str, Any]]:
        """
        Get an article along with surrounding articles (context windowing).
        Fetches N articles before and after from the same normativa.
        
        Note: Since structural nodes are no longer stored, siblings are articles
        in the same normativa ordered by name.
        
        Args:
            article_id: ID of the target article
            context_window: Number of articles to fetch before/after
            
        Returns:
            Dict with target article and context articles
        """
        query = """
        MATCH (target:articulo {id: $article_id})-[:PART_OF]->(normativa:Normativa)
        
        // Get all articles in the same normativa
        MATCH (sibling:articulo)-[:PART_OF]->(normativa)
        
        WITH target, normativa, collect(DISTINCT sibling) as all_articles
        
        RETURN 
            target.id as article_id,
            target.name as article_number,
            target.full_text as article_text,
            target.embedding as embedding,
            target.path as context_path,
            normativa.titulo as normativa_title,
            normativa.id as normativa_id,
            [s in all_articles | {id: s.id, name: s.name, text: s.full_text}] as surrounding_articles
        """
        
        with self.conn._driver.session() as session:
            result = session.run(query, {"article_id": article_id})
            record = result.single()
            return dict(record) if record else None
    
    def get_articles_by_structure(self, structure_pattern: str, 
                                 normativa_id: str = None) -> List[Dict[str, Any]]:
        """
        Get all articles within a specific structural element using path property.
        
        Since structural nodes are no longer stored in the graph, this method
        uses the `path` property on articles to filter by structure.
        
        Args:
            structure_pattern: Pattern to match in path (e.g., "Titulo I", "Capitulo II")
            normativa_id: Optional normativa ID to scope the search
            
        Returns:
            List of articles matching the structure pattern
        """
        if normativa_id:
            query = """
            MATCH (article:articulo)-[:PART_OF]->(normativa:Normativa {id: $normativa_id})
            WHERE article.path CONTAINS $structure_pattern
            RETURN 
                article.id as article_id,
                article.name as article_number,
                article.full_text as article_text,
                article.embedding as embedding,
                article.path as context_path,
                normativa.titulo as normativa_title,
                normativa.id as normativa_id
            ORDER BY article.name
            """
            params = {"structure_pattern": structure_pattern, "normativa_id": normativa_id}
        else:
            query = """
            MATCH (article:articulo)-[:PART_OF]->(normativa:Normativa)
            WHERE article.path CONTAINS $structure_pattern
            RETURN 
                article.id as article_id,
                article.name as article_number,
                article.full_text as article_text,
                article.embedding as embedding,
                article.path as context_path,
                normativa.titulo as normativa_title,
                normativa.id as normativa_id
            ORDER BY article.name
            """
            params = {"structure_pattern": structure_pattern}
        
        with self.conn._driver.session() as session:
            result = session.run(query, params)
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
        MATCH (article:articulo {id: $article_id})
        
        // Get all previous versions
        OPTIONAL MATCH path1 = (article)-[:PREVIOUS_VERSION*]->(older)
        WITH article, collect(DISTINCT older) as previous_versions
        
        // Get all next versions
        OPTIONAL MATCH path2 = (article)-[:NEXT_VERSION*]->(newer)
        WITH article, previous_versions, collect(DISTINCT newer) as next_versions
        
        // Combine all versions
        WITH previous_versions + [article] + next_versions as all_versions
        UNWIND all_versions as version
        
        MATCH (version)-[:PART_OF*]->(normativa:Normativa)
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
    
    def get_articles_by_subject(self, materia_id: str) -> List[Dict[str, Any]]: # might need updaing
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
        // Traversing down from Normativa is tricky without HAS_CONTENT root, so utilize PART_OF upwards from articles?
        // But we want ALL articles for a subject (normativa).
        // Since Normativa is now the root of hierarchy:
        MATCH (article:articulo)-[:PART_OF*]->(normativa)
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


    def get_article_rich_text(self, article_id: str) -> Optional[str]:
        """
        Get article text with proper formatting and indentation based on nesting depth.
        
        Args:
            article_id: ID of the article node
            
        Returns:
            Formatted article text with indentation for nested elements
        """
        query = """
        MATCH (parent:articulo {id: $article_id})
        MATCH path = (child)-[:PART_OF*]->(parent)
        WITH child, length(path) as depth
        RETURN 
            child.id AS node_id,
            child.name AS node_name,
            child.text AS node_text,
            labels(child) AS node_labels,
            depth
        ORDER BY child.id
        """

        text = ""
        INDENT = "  "  # Two spaces per indentation level

        with self.conn._driver.session() as session:
            result = session.run(query, {"article_id": article_id})
            for node in result:
                node_labels = node["node_labels"]
                node_name = node["node_name"]
                node_text = node["node_text"]
                depth = node["depth"]
                
                # Calculate indentation (depth 1 = no indent, depth 2+ = indent)
                indent = INDENT * (depth - 1) if depth > 1 else ""
                
                if node_labels == ["parrafo"]:
                    text += indent + node_text + "\n"
                elif node_labels == ["apartado_numerico"]:
                    text += indent + node_name + ". " + node_text + "\n"
                elif node_labels == ["apartado_alfa"]:
                    text += indent + node_name + ") " + node_text + "\n"
                elif node_labels == ["ordinal_alfa"]:
                    text += indent + node_name + node_text + "\n"
                elif node_labels == ["ordinal_numerico"]:
                    text += indent + node_name + node_text + "\n"

            return text.strip() if text else None

    def get_article_by_id(self, node_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single article by its node ID with full metadata.
        
        Args:
            node_id: ID of the article node
            
        Returns:
            Dict with article data, dates, and version links
        """
        query = """
        MATCH (node:articulo {id: $node_id})
        MATCH (node)-[:PART_OF*]->(parent)
        WITH node, collect(parent) as hierarchy
        MATCH (node)-[:PART_OF*]->(normativa:Normativa)
        
        // Check for version relationships
        OPTIONAL MATCH (node)<-[:NEXT_VERSION]-(prev_version)
        OPTIONAL MATCH (node)-[:NEXT_VERSION]->(next_version)
        
        RETURN 
            node.id as node_id,
            node.name as article_number,
            node.full_text as article_text,
            node.path as article_path,
            node.fecha_vigencia as fecha_vigencia,
            node.fecha_caducidad as fecha_caducidad,
            normativa.fecha_publicacion as fecha_publicacion,
            prev_version.id as previous_version_id,
            next_version.id as next_version_id,
            normativa.titulo as normativa_title,
            normativa.id as normativa_id,
            [h in hierarchy | {type: labels(h)[0], name: h.name}] as context_path
        """
        
        with self.conn._driver.session() as session:
            result = session.run(query, {"node_id": node_id})
            record = result.single()
            return dict(record) if record else None

    def get_version_text(self, node_id: str) -> Optional[str]:
        """
        Get the full text of an article by node ID.
        Used for fetching version context in RAG.
        
        Args:
            node_id: ID of the article node
            
        Returns:
            The article's full_text or None if not found
        """
        query = """
        MATCH (node:articulo {id: $node_id})
        RETURN node.full_text as text
        """
        
        with self.conn._driver.session() as session:
            result = session.run(query, {"node_id": node_id})
            record = result.single()
            return record["text"] if record else None

    def get_all_next_versions(self, node_id: str) -> List[Dict[str, Any]]:
        """
        Recursively get all subsequent versions of an article.
        
        Args:
            node_id: ID of the starting article node
            
        Returns:
            List of version data ordered chronologically (oldest first)
        """
        query = """
        MATCH (start:articulo {id: $node_id})
        MATCH path = (start)-[:NEXT_VERSION*]->(version)
        RETURN 
            version.id as node_id,
            version.name as article_number,
            version.full_text as article_text,
            version.fecha_vigencia as fecha_vigencia,
            version.fecha_caducidad as fecha_caducidad
        ORDER BY version.fecha_vigencia
        """
        
        with self.conn._driver.session() as session:
            result = session.run(query, {"node_id": node_id})
            return [dict(record) for record in result]

    def get_previous_version(self, node_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the immediate previous version of an article.
        
        Args:
            node_id: ID of the article node
            
        Returns:
            Previous version data or None if not found
        """
        query = """
        MATCH (node:articulo {id: $node_id})
        MATCH (node)<-[:NEXT_VERSION]-(prev)
        RETURN 
            prev.id as node_id,
            prev.name as article_number,
            prev.full_text as article_text,
            prev.fecha_vigencia as fecha_vigencia,
            prev.fecha_caducidad as fecha_caducidad
        """
        
        with self.conn._driver.session() as session:
            result = session.run(query, {"node_id": node_id})
            record = result.single()
            return dict(record) if record else None

    def get_latest_version(self, article_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the latest version of an article by following NEXT_VERSION chain.
        
        If the article has no newer versions, returns the article itself.
        Used for RAG validity checking to ensure context is current.
        
        Args:
            article_id: ID of any version of the article
            
        Returns:
            Latest version's data with normativa context
        """
        query = """
        MATCH (start:articulo {id: $article_id})
        OPTIONAL MATCH path = (start)-[:NEXT_VERSION*]->(latest)
        WHERE NOT (latest)-[:NEXT_VERSION]->()
        WITH COALESCE(last(nodes(path)), start) as current
        MATCH (current)-[:PART_OF*1..10]->(normativa:Normativa)
        RETURN 
            current.id as article_id,
            current.name as article_number,
            current.full_text as article_text,
            current.path as article_path,
            current.fecha_vigencia as fecha_vigencia,
            current.fecha_caducidad as fecha_caducidad,
            normativa.titulo as normativa_title,
            normativa.id as normativa_id
        """
        return self.run_query_single(query, {"article_id": article_id})

    def get_referred_articles(self, article_id: str, max_refs: int = 3) -> List[Dict[str, Any]]:
        """
        Get articles that this article REFERS_TO.
        
        Used for RAG reference expansion to include related legal articles.
        
        Args:
            article_id: ID of the source article
            max_refs: Maximum number of referenced articles to return
            
        Returns:
            List of referenced article data with normativa context
        """
        query = """
        MATCH (source:articulo {id: $article_id})-[:REFERS_TO]->(target:articulo)
        MATCH (target)-[:PART_OF*1..10]->(normativa:Normativa)
        WITH DISTINCT target, normativa
        RETURN 
            target.id as article_id,
            target.name as article_number,
            target.full_text as article_text,
            target.path as article_path,
            target.fecha_vigencia as fecha_vigencia,
            normativa.titulo as normativa_title,
            normativa.id as normativa_id
        LIMIT $max_refs
        """
        return self.run_query(query, {"article_id": article_id, "max_refs": max_refs})