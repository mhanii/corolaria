"""
Centralized article text construction for consistency across the pipeline.

This service provides a single source of truth for building article text
representations, eliminating duplication between embedding generation,
Neo4j storage, and API retrieval.
"""
from typing import Optional, TYPE_CHECKING
from datetime import datetime

from src.domain.models.common.node import Node, NodeType, ArticleNode

if TYPE_CHECKING:
    from src.domain.models.normativa import NormativaCons


class ArticleTextBuilder:
    """
    Builds consistent text representations for articles.
    
    Used by:
    - EmbeddingGenerator: For semantic embedding context
    - NormativaRepository: For pre-computing full_text on Neo4j nodes
    - API retrieval: Returns stored full_text directly (no reconstruction)
    """
    
    def build_full_text(self, article: ArticleNode) -> str:
        """
        Build the complete text content of an article including all children.
        
        This is stored in Neo4j as `full_text` for efficient retrieval.
        Format includes proper indentation based on element types.
        
        Args:
            article: The article node to build text for
            
        Returns:
            Formatted article text with all nested content
        """
        parts = []
        
        # Add article's direct text if present
        if article.text:
            parts.append(article.text)
        
        # Recursively collect child text with formatting
        if article.content:
            for child in article.content:
                if isinstance(child, Node):
                    parts.extend(self._get_node_text(child, depth=0))
        
        return "\n\n".join(parts) if parts else ""
    
    def _get_node_text(self, node: Node, depth: int = 0) -> list:
        """
        Recursively get formatted text from a node and its children.
        
        Args:
            node: The node to extract text from
            depth: Current nesting depth for indentation
            
        Returns:
            List of formatted text strings
        """
        texts = []
        prefix = ""
        
        # Format based on node type
        if node.node_type == NodeType.APARTADO_NUMERICO:
            prefix = f"{node.name}. "
        elif node.node_type == NodeType.APARTADO_ALFA:
            prefix = f"{node.name}) "
        elif node.node_type == NodeType.ORDINAL_ALFA:
            prefix = f"{node.name} "
        elif node.node_type == NodeType.ORDINAL_NUMERICO:
            prefix = f"{node.name} "
        # PARRAFO has no prefix
        
        full_text = f"{prefix}{node.text}" if node.text else ""
        if full_text:
            texts.append(full_text)
        
        # Recurse into children
        if node.content:
            for child in node.content:
                if isinstance(child, Node):
                    texts.extend(self._get_node_text(child, depth + 1))
        
        return texts
    
    def build_hierarchy_path(self, article: ArticleNode) -> str:
        """
        Build a human-readable hierarchy path for the article.
        
        Format: "Título I, Capítulo II, Sección 1.ª"
        This is stored in Neo4j as `path` for display in search results.
        
        Args:
            article: The article node
            
        Returns:
            Formatted hierarchy path string
        """
        hierarchy = article.get_hierarchy_path()
        
        # Filter out ROOT, ARTICULO types - we want structural context only
        excluded_types = {NodeType.ROOT, NodeType.ARTICULO, NodeType.ARTICULO_UNICO}
        context_nodes = [n for n in hierarchy if n.node_type not in excluded_types]
        
        if not context_nodes:
            return ""
        
        # Format each structural element
        formatted = []
        for node in context_nodes:
            type_name = node.node_type.value.capitalize()
            formatted.append(f"{type_name} {node.name}")
        
        return ", ".join(formatted)
    
    def build_context_string(self, normativa: 'NormativaCons', article: ArticleNode) -> str:
        """
        Build full context string for semantic embeddings.
        
        Format:

        Documento: {Title} ({ID})
        Contexto: {Libro > Título > Capítulo}
        Artículo: {Número}
        Estado: {Vigencia} (NL)
        Contenido:
        {Texto del artículo}
        
        Args:
            normativa: The parent normativa document
            article: The article node
            
        Returns:
            Complete context string for embedding
        """
        # 1. Document info
        doc_info = f"Documento: {normativa.metadata.titulo} ({normativa.id})"
        
        # 2. Hierarchy context (use > separator for embeddings)
        hierarchy = article.get_hierarchy_path()
        excluded_types = {NodeType.ROOT, NodeType.ARTICULO, NodeType.ARTICULO_UNICO}
        context_nodes = [n for n in hierarchy if n.node_type not in excluded_types]
        
        if context_nodes:
            context_str = " > ".join([f"{n.node_type.value.capitalize()} {n.name}" for n in context_nodes])
        else:
            context_str = "General"
        context_line = f"Contexto: {context_str}"
        
        # 3. Article info
        article_line = f"Artículo: {article.name}"
        
        # 4. State (vigencia)
        state_line = self._build_state_line(article)
        
        # 5. Content
        content_text = self.build_full_text(article)
        
        # Assemble
        return f"{doc_info}\n{context_line}\n{article_line}\n{state_line}\nContenido:\n{content_text}"
    
    def _build_state_line(self, article: ArticleNode) -> str:
        """Build the vigencia state line for an article.
        
        Uses semantically rich Spanish phrasing for better RAG embedding.
        We only describe the state, not the reason (derogation vs modification),
        since ArticleNode only has dates, not explicit reason flags.
        """
        start_date = self._format_date_human(article.fecha_vigencia)
        
        is_active = True
        if article.fecha_caducidad or article.next_version:
            is_active = False
        
        if not is_active and article.fecha_caducidad:
            # Article has an end date - could be derogation, modification, or natural expiry
            end_date = self._format_date_human(article.fecha_caducidad)
            return f"Estado: Este artículo ya no está en vigor. Estuvo vigente desde {start_date} hasta {end_date}."
        elif not is_active:
            # Article was replaced by a newer version (has next_version but no end date)
            return f"Estado: Este artículo ha sido modificado. Existe una versión más reciente. Estuvo vigente desde {start_date}."
        else:
            # Article is currently active
            return f"Estado: Este artículo está actualmente vigente desde {start_date}. Se encuentra en vigor."
    
    def _format_date_human(self, date_str: Optional[str]) -> str:
        """Format a date string to Spanish human-readable format."""
        if not date_str:
            return "Desconocida"
        try:
            dt = datetime.fromisoformat(date_str)
            months = [
                "enero", "febrero", "marzo", "abril", "mayo", "junio",
                "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
            ]
            return f"{dt.day} de {months[dt.month - 1]} de {dt.year}"
        except ValueError:
            return date_str
