"""
Abstract interface for graph database operations.
Domain services depend on this abstraction, not concrete implementations.
This enforces the Dependency Inversion Principle in Clean Architecture.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class GraphAdapter(ABC):
    """
    Abstract interface for graph database operations.
    
    Domain layer services should depend on this interface, not on
    concrete implementations like Neo4jAdapter. This allows:
    - Easy testing with mock implementations
    - Swapping graph databases without changing domain code
    - Clear separation between domain and infrastructure layers
    """
    
    @abstractmethod
    def vector_search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        label: str = "articulo",
        index_name: str = "article_embeddings",
        min_score: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Perform vector similarity search.
        
        Args:
            query_embedding: The embedding vector to search for
            top_k: Number of results to return
            label: Node label to search
            index_name: Name of the vector index
            min_score: Minimum similarity score threshold
            
        Returns:
            List of article dicts with similarity scores
        """
        pass
    
    @abstractmethod
    def keyword_search(
        self,
        keywords: str,
        top_k: int = 10,
        label: str = "articulo"
    ) -> List[Dict[str, Any]]:
        """
        Perform keyword search on article text.
        
        Args:
            keywords: Search keywords
            top_k: Number of results to return
            label: Node label to search
            
        Returns:
            List of matching articles
        """
        pass
    
    @abstractmethod
    def get_article_by_id(self, node_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single article by its node ID.
        
        Args:
            node_id: ID of the article node
            
        Returns:
            Dict with article data or None if not found
        """
        pass
    
    @abstractmethod
    def get_article_with_context(
        self,
        article_id: str,
        context_window: int = 2
    ) -> Optional[Dict[str, Any]]:
        """
        Get an article with surrounding context articles.
        
        Args:
            article_id: ID of the target article
            context_window: Number of articles to fetch before/after
            
        Returns:
            Dict with target article and context articles
        """
        pass
    
    @abstractmethod
    def get_article_versions(self, article_id: str) -> List[Dict[str, Any]]:
        """
        Get all versions of an article.
        
        Args:
            article_id: ID of any version of the article
            
        Returns:
            List of all versions ordered chronologically
        """
        pass
    
    @abstractmethod
    def get_all_next_versions(self, node_id: str) -> List[Dict[str, Any]]:
        """
        Recursively get all subsequent versions of an article.
        
        Args:
            node_id: ID of the starting article node
            
        Returns:
            List of version data ordered chronologically
        """
        pass
    
    @abstractmethod
    def get_previous_version(self, node_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the immediate previous version of an article.
        
        Args:
            node_id: ID of the article node
            
        Returns:
            Previous version data or None if not found
        """
        pass
    
    @abstractmethod
    def get_latest_version(self, article_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the latest version of an article.
        
        Args:
            article_id: ID of any version of the article
            
        Returns:
            Latest version's data
        """
        pass
    
    @abstractmethod
    def get_referred_articles(
        self,
        article_id: str,
        max_refs: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Get articles that this article references.
        
        Args:
            article_id: ID of the source article
            max_refs: Maximum number of referenced articles
            
        Returns:
            List of referenced article data
        """
        pass
    
    @abstractmethod
    def get_article_rich_text(self, article_id: str) -> Optional[str]:
        """
        Get article text with proper formatting.
        
        Args:
            article_id: ID of the article node
            
        Returns:
            Formatted article text or None
        """
        pass
    
    @abstractmethod
    def get_version_text(self, node_id: str) -> Optional[str]:
        """
        Get the full text of an article by node ID.
        
        Args:
            node_id: ID of the article node
            
        Returns:
            The article's full_text or None
        """
        pass
    
    @abstractmethod
    def get_articles_by_structure(
        self,
        structure_pattern: str,
        normativa_id: str = None
    ) -> List[Dict[str, Any]]:
        """
        Get all articles within a specific structural element.
        
        Args:
            structure_pattern: Pattern to match in article path
            normativa_id: Optional normativa filter
            
        Returns:
            List of articles matching the structure
        """
        pass
    
    @abstractmethod
    def get_articles_by_subject(self, materia_id: str) -> List[Dict[str, Any]]:
        """
        Get all articles related to a subject matter.
        
        Args:
            materia_id: ID of the Materia node
            
        Returns:
            List of articles about that subject
        """
        pass
    
    # ========== Write Operations ==========
    # Used by repositories for data ingestion
    
    @abstractmethod
    def merge_node(
        self,
        labels: List[str],
        properties: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Create or merge a node with given labels and properties.
        
        Args:
            labels: List of node labels
            properties: Node properties (must include 'id')
            
        Returns:
            Dict with node id or None if failed
        """
        pass
    
    @abstractmethod
    def merge_relationship(
        self,
        from_id: str,
        to_id: str,
        rel_type: str,
        properties: Optional[Dict[str, Any]] = None,
        from_label: Optional[str] = None,
        to_label: Optional[str] = None
    ) -> Any:
        """
        Create or merge a relationship between two nodes.
        
        Args:
            from_id: Source node ID
            to_id: Target node ID
            rel_type: Relationship type
            properties: Optional relationship properties
            from_label: Optional source node label (for index usage)
            to_label: Optional target node label (for index usage)
            
        Returns:
            Relationship data or None
        """
        pass
    
    @abstractmethod
    def batch_merge_nodes(self, nodes_data: List[Dict[str, Any]]) -> None:
        """
        Batch create/merge multiple nodes for performance.
        
        Args:
            nodes_data: List of dicts with 'labels' (list) and 'props' (dict)
                       Example: [{"labels": ["articulo"], "props": {"id": "...", ...}}]
        """
        pass
    
    @abstractmethod
    def batch_merge_relationships(self, relationships_data: List[Dict[str, Any]]) -> None:
        """
        Batch create/merge multiple relationships for performance.
        
        Args:
            relationships_data: List of dicts with:
                - 'from_id': Source node ID
                - 'to_id': Target node ID  
                - 'rel_type': Relationship type
                - 'props': Optional relationship properties
                - 'from_label': Optional source node label (for index usage)
                - 'to_label': Optional target node label (for index usage)
        """
        pass
    
    # ========== Query Execution ==========
    # Low-level query methods for repositories
    
    @abstractmethod
    def run_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute a read query and return all results.
        
        Args:
            query: Query string (e.g., Cypher for Neo4j)
            parameters: Query parameters
            
        Returns:
            List of record dictionaries
        """
        pass
    
    @abstractmethod
    def run_query_single(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Execute a read query and return a single result.
        
        Args:
            query: Query string
            parameters: Query parameters
            
        Returns:
            Single record dictionary or None
        """
        pass
    
    @abstractmethod
    def run_write(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Execute a write query and return the result.
        
        Args:
            query: Query string (e.g., Cypher for Neo4j)
            parameters: Query parameters
            
        Returns:
            Single record dictionary or None
        """
        pass
    
    # ========== Index Operations ==========
    # Used by indexing layer
    
    @abstractmethod
    def create_vector_index(
        self,
        index_name: str,
        label: str,
        property_name: str,
        dimensions: int,
        similarity_function: str
    ) -> None:
        """
        Create a vector index for similarity search.
        
        Args:
            index_name: Name of the index
            label: Node label to index
            property_name: Property containing embeddings
            dimensions: Vector dimensions
            similarity_function: Similarity function (e.g., 'cosine')
        """
        pass
