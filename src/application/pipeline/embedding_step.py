from typing import List, Optional
import hashlib
from src.application.pipeline.base import Step
from src.domain.models.normativa import NormativaCons
from src.domain.models.common.node import Node, NodeType, ArticleNode
from src.domain.interfaces.embedding_provider import EmbeddingProvider
from src.domain.interfaces.embedding_cache import EmbeddingCache
from src.domain.services.article_text_builder import ArticleTextBuilder
from src.utils.logger import step_logger, output_logger

class EmbeddingGenerator(Step):
    def __init__(self, name: str, provider: EmbeddingProvider, cache: Optional[EmbeddingCache] = None):
        super().__init__(name)
        self.provider = provider
        self.cache = cache
        self.text_builder = ArticleTextBuilder()
        
        # Import tracing (optional)
        try:
            from opentelemetry import trace
            self._tracer = trace.get_tracer("embedding_generator")
            self._trace = trace
        except ImportError:
            self._tracer = None
            self._trace = None

    def process(self, data):
        """
        Process the Normativa document and generate embeddings for all articles.
        """
        normativa, change_events = data
        
        if not normativa:
            step_logger.warning("Normativa is empty, skipping embedding generation.")
            return data

        step_logger.info(f"Generating embeddings using model: {self.provider.model}")
        
        # Add tracing input attributes
        if self._tracer:
            current_span = self._trace.get_current_span()
            if current_span and current_span.is_recording():
                current_span.set_attribute("embedding.model", self.provider.model)
                current_span.set_attribute("embedding.normativa_id", normativa.id)
        
        # Traverse the tree and collect articles
        articles = self._collect_articles(normativa.content_tree)
        step_logger.info(f"Found {len(articles)} articles to embed.")

        if not articles:
            return data

        # Prepare texts for embedding
        texts_to_embed = []
        articles_to_embed = []
        
        cache_hits = 0
        
        for article in articles:
            # Use centralized text builder for consistency
            context_text = self.text_builder.build_context_string(normativa, article)
            output_logger.info(f"\n--- [EmbeddingGenerator] Processing Article {article.id} ---\n{context_text}\n")
            
            # Check cache
            embedding = None
            if self.cache:
                context_hash = hashlib.sha256(context_text.encode('utf-8')).hexdigest()
                embedding = self.cache.get(context_hash)
            
            if embedding:
                article.embedding = embedding
                cache_hits += 1
            else:
                texts_to_embed.append(context_text)
                articles_to_embed.append(article)

        step_logger.info(f"Cache hits: {cache_hits}. Articles to embed: {len(articles_to_embed)}")
        
        embeddings_generated = 0

        # Generate embeddings for misses
        if articles_to_embed:
            try:
                embeddings = self.provider.get_embeddings(texts_to_embed)
                embeddings_generated = len(embeddings)
                
                # Assign embeddings back to nodes and update cache
                for article, text, embedding in zip(articles_to_embed, texts_to_embed, embeddings):
                    article.embedding = embedding
                    if self.cache:
                        context_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
                        self.cache.set(context_hash, embedding)
                    
                step_logger.info(f"Successfully generated {len(embeddings)} embeddings.")
                
                # Persist cache
                if self.cache:
                    self.cache.save()
                
            except Exception as e:
                step_logger.error(f"Error generating embeddings: {e}")
                # We might want to raise or return None depending on strictness. 
                # For now, we log and proceed (articles will have None embedding).

        # Add tracing output attributes
        if self._tracer:
            current_span = self._trace.get_current_span()
            if current_span and current_span.is_recording():
                current_span.set_attribute("embedding.total_articles", len(articles))
                current_span.set_attribute("embedding.cache_hits", cache_hits)
                current_span.set_attribute("embedding.embeddings_generated", embeddings_generated)
                current_span.set_attribute("embedding.cache_hit_rate", f"{cache_hits/len(articles)*100:.1f}%" if articles else "N/A")

        return data

    def _collect_articles(self, node: Node) -> List[ArticleNode]:
        """Recursively find all ArticleNodes in the tree."""
        articles = []
        if isinstance(node, ArticleNode):
            articles.append(node)
        
        if node.content:
            for child in node.content:
                if isinstance(child, Node): # Ensure it's a Node (not string)
                    articles.extend(self._collect_articles(child))
        
        return articles

    def _build_context_string(self, normativa: NormativaCons, article: ArticleNode) -> str:
        """
        Construct the rich text representation for the article.
        Format:
        Documento: {Title} ({ID})
        Contexto: {Libro} > {Título} > {Capítulo}
        Artículo: {Número}
        Estado: {Vigencia}
        Contenido:
        {Texto del artículo}
        """
        from datetime import datetime
        
        def format_date_human(date_str: str) -> str:
            if not date_str:
                return "Desconocida"
            try:
                dt = datetime.fromisoformat(date_str)
                # Format: 29 de diciembre de 1978
                months = [
                    "enero", "febrero", "marzo", "abril", "mayo", "junio", 
                    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
                ]
                return f"{dt.day} de {months[dt.month - 1]} de {dt.year}"
            except ValueError:
                return date_str

        # 1. Document Info
        doc_info = f"Documento: {normativa.metadata.titulo} ({normativa.id})"
        
        # 2. Hierarchy Context
        hierarchy_path = article.get_hierarchy_path()
        # Filter out ROOT and the Article itself to get the "path"
        context_nodes = [n for n in hierarchy_path if n.node_type not in (NodeType.ROOT, NodeType.ARTICULO, NodeType.ARTICULO_UNICO)]
        context_str = " > ".join([f"{n.node_type.value.capitalize()} {n.name}" for n in context_nodes])
        if not context_str:
            context_str = "General"
        context_line = f"Contexto: {context_str}"
        
        # 3. Article Info
        article_line = f"Artículo: {article.name}"
        
        # 4. State (Vigencia)
        start_date = format_date_human(article.fecha_vigencia)
        
        is_active = True
        if article.fecha_caducidad or article.next_version:
            is_active = False
            
        if not is_active and article.fecha_caducidad:
            end_date = format_date_human(article.fecha_caducidad)
            state_line = f"Estado: Vigente desde {start_date} hasta {end_date}"
        elif not is_active:
             # Has next version but no explicit end date (or we don't know it), imply it's not current
             state_line = f"Estado: No vigente (desde {start_date})"
        else:
            state_line = f"Estado: Vigente desde {start_date}"
        
        # 5. Content
        # Concatenate text from the article node and its children (paragraphs)
        content_parts = []
        if article.text:
            content_parts.append(article.text)
        
        # Helper to recursively get text from children with formatting
        def get_child_text(n: Node, depth=0):
            texts = []
            prefix = ""
            
            # Add indentation/formatting based on type
            # We assume 'name' holds the marker (1, a, etc.)
            if n.node_type == NodeType.APARTADO_NUMERICO:
                prefix = f"{n.name}. "
            elif n.node_type == NodeType.APARTADO_ALFA:
                prefix = f"{n.name}) "
            elif n.node_type == NodeType.PARRAFO:
                pass # Paragraphs usually just text
                
            full_text = f"{prefix}{n.text}" if n.text else ""
            
            # Add newline before list items for readability if not first
            if full_text:
                texts.append(full_text)
            
            if n.content:
                for c in n.content:
                    if isinstance(c, Node):
                        texts.extend(get_child_text(c, depth + 1))
            return texts

        if article.content:
            for child in article.content:
                if isinstance(child, Node):
                    content_parts.extend(get_child_text(child))
        
        # Join with double newlines for clear separation of paragraphs/items
        content_text = "\n\n".join(content_parts)
        
        # Final Assembly
        full_text = f"{doc_info}\n{context_line}\n{article_line}\n{state_line}\nContenido:\n{content_text}"
        
        return full_text

    # Note: _build_context_string has been moved to ArticleTextBuilder for consistency.
    # This method is kept temporarily for backwards compatibility but delegates to the builder.
    def _build_context_string(self, normativa: NormativaCons, article: ArticleNode) -> str:
        """Deprecated: Use self.text_builder.build_context_string() instead."""
        return self.text_builder.build_context_string(normativa, article)
