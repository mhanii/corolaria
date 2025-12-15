"""
Agent Tools for AgentCollector.

Provides tool definitions using LangChain's @tool decorator
for use with LangGraph's prebuilt agents.

Uses closure pattern to inject dependencies (graph_adapter, embedding_provider)
into tools while keeping them compatible with LangGraph's create_react_agent.
"""
from typing import List, Dict, Any
from langchain_core.tools import tool

from src.domain.interfaces.graph_adapter import GraphAdapter
from src.domain.interfaces.embedding_provider import EmbeddingProvider
from src.utils.logger import step_logger


class ContextAccumulator:
    """
    Accumulates context chunks during agent execution.
    
    Shared between tools to track which articles have been added to context.
    """
    
    def __init__(self):
        self._chunks: List[Dict[str, Any]] = []
        self._ids: set = set()
        self._cache: Dict[str, Dict[str, Any]] = {}
    
    @property
    def chunks(self) -> List[Dict[str, Any]]:
        return self._chunks.copy()
    
    def add(self, article: Dict[str, Any]) -> bool:
        """Add article to context. Returns True if added, False if duplicate."""
        article_id = article.get("article_id")
        if article_id in self._ids:
            return False
        self._chunks.append(article)
        self._ids.add(article_id)
        return True
    
    def cache(self, article_id: str, article: Dict[str, Any]):
        """Cache retrieved article for later use."""
        self._cache[article_id] = article
    
    def get_cached(self, article_id: str) -> Dict[str, Any] | None:
        """Get cached article by ID."""
        return self._cache.get(article_id)
    
    def reset(self):
        """Reset for new query."""
        self._chunks = []
        self._ids = set()
        self._cache = {}


def create_agent_tools(
    graph_adapter: GraphAdapter,
    embedding_provider: EmbeddingProvider,
    context_accumulator: ContextAccumulator,
    index_name: str = "article_embeddings"
) -> List:
    """
    Create tools for the agent using closure pattern.
    
    Args:
        graph_adapter: Neo4j adapter for graph queries
        embedding_provider: Embeddings for semantic search
        context_accumulator: Shared context accumulator
        index_name: Vector index name
        
    Returns:
        List of LangChain tools
    """
    
    @tool
    def run_rag_query(query: str, top_k: int = 5) -> str:
        """
        Search for relevant legal articles using semantic similarity.
        
        Use this to find articles related to a topic or concept.
        Returns a list of matching articles with previews.
        
        Args:
            query: Natural language search query in Spanish
            top_k: Maximum number of results (default: 5)
        """
        step_logger.info(f"[AgentTools] run_rag_query: '{query[:50]}...' (top_k={top_k})")
        
        try:
            # Generate query embedding
            query_embedding = embedding_provider.get_embedding(query)
            
            # Vector search
            results = graph_adapter.vector_search(
                query_embedding=query_embedding,
                top_k=top_k,
                index_name=index_name
            )
            
            # Cache results and format output
            output_lines = [f"Found {len(results)} articles:\n"]
            for i, r in enumerate(results, 1):
                article_id = r.get("article_id", "unknown")
                context_accumulator.cache(article_id, r)
                
                preview = (r.get("article_text") or r.get("full_text", ""))[:150]
                output_lines.append(
                    f"{i}. [{article_id}] {r.get('article_number', 'Article')} - "
                    f"{r.get('normativa_title', 'Unknown')[:50]}\n"
                    f"   Preview: {preview}...\n"
                    f"   Score: {r.get('score', 0):.3f}\n"
                )
            
            step_logger.info(f"[AgentTools] run_rag_query returned {len(results)} results")
            return "\n".join(output_lines)
            
        except Exception as e:
            step_logger.error(f"[AgentTools] run_rag_query error: {e}")
            return f"Search failed: {str(e)}"
    
    @tool
    def add_to_context(article_ids: List[str]) -> str:
        """
        Add articles to the final context for answering the user's question.
        
        Call this after finding relevant articles with run_rag_query.
        Only added articles will be used to generate the final answer.
        
        Args:
            article_ids: List of article IDs to add (from search results)
        """
        step_logger.info(f"[AgentTools] add_to_context: {article_ids}")
        
        added = []
        skipped = []
        not_found = []
        
        for article_id in article_ids:
            # Try cache first
            article = context_accumulator.get_cached(article_id)
            
            # Fetch from database if not cached
            if not article:
                article = graph_adapter.get_article_by_id(article_id)
            
            if article:
                if context_accumulator.add(article):
                    added.append(article_id)
                else:
                    skipped.append(article_id)
            else:
                not_found.append(article_id)
        
        # Build response
        parts = []
        if added:
            parts.append(f"Added {len(added)} articles: {added}")
        if skipped:
            parts.append(f"Already in context: {skipped}")
        if not_found:
            parts.append(f"Not found: {not_found}")
        
        result = ". ".join(parts) if parts else "No changes"
        total = len(context_accumulator.chunks)
        result += f"\nTotal articles in context: {total}"
        
        step_logger.info(f"[AgentTools] add_to_context result: added={len(added)}, total={total}")
        return result
    
    @tool
    def keyword_search(word: str, top_k: int = 10) -> str:
        """
        Search for articles containing a specific keyword or phrase.
        
        Use for finding articles with exact terms (e.g., law names, legal concepts).
        
        Args:
            word: Keyword or phrase to search for
            top_k: Maximum results (default: 10)
        """
        step_logger.info(f"[AgentTools] keyword_search: '{word}' (top_k={top_k})")
        
        try:
            results = graph_adapter.keyword_search(keywords=word, top_k=top_k)
            
            if not results:
                return f"No articles found containing '{word}'"
            
            output_lines = [f"Found {len(results)} articles containing '{word}':\n"]
            for i, r in enumerate(results, 1):
                article_id = r.get("article_id", "unknown")
                context_accumulator.cache(article_id, r)
                
                preview = (r.get("article_text") or r.get("full_text", ""))[:100]
                output_lines.append(
                    f"{i}. [{article_id}] {r.get('article_number', 'Article')} - "
                    f"{r.get('normativa_title', 'Unknown')[:40]}\n"
                    f"   Preview: {preview}...\n"
                )
            
            return "\n".join(output_lines)
            
        except Exception as e:
            step_logger.error(f"[AgentTools] keyword_search error: {e}")
            return f"Search failed: {str(e)}"
    
    @tool
    def hybrid_vector_search(query: str, top_k: int = 10) -> str:
        """
        Advanced semantic search with connectivity-based reranking.
        
        Finds relevant articles and reranks by how connected they are
        (articles cited by many others rank higher).
        
        Args:
            query: Natural language search query
            top_k: Maximum results (default: 10)
        """
        step_logger.info(f"[AgentTools] hybrid_vector_search: '{query[:50]}...'")
        
        try:
            # Step 1: Vector search
            query_embedding = embedding_provider.get_embedding(query)
            results = graph_adapter.vector_search(
                query_embedding=query_embedding,
                top_k=top_k * 2,  # Get more for reranking
                index_name=index_name
            )
            
            if not results:
                return "No articles found"
            
            # Step 2: Compute connectivity scores
            for r in results:
                article_id = r.get("article_id")
                # Count incoming references (how many articles cite this one)
                try:
                    in_refs = len(graph_adapter.get_referred_articles(article_id, max_refs=20))
                except:
                    in_refs = 0
                
                base_score = r.get("score", 0)
                r["connectivity_score"] = in_refs
                r["final_score"] = base_score + (in_refs * 0.05)
            
            # Step 3: Rerank by final score
            results.sort(key=lambda x: x.get("final_score", 0), reverse=True)
            results = results[:top_k]
            
            # Format output
            output_lines = [f"Found {len(results)} articles (reranked by connectivity):\n"]
            for i, r in enumerate(results, 1):
                article_id = r.get("article_id", "unknown")
                context_accumulator.cache(article_id, r)
                
                preview = (r.get("article_text") or r.get("full_text", ""))[:100]
                output_lines.append(
                    f"{i}. [{article_id}] {r.get('article_number', 'Article')} - "
                    f"{r.get('normativa_title', 'Unknown')[:40]}\n"
                    f"   Connectivity: {r.get('connectivity_score', 0)} refs | "
                    f"Score: {r.get('final_score', 0):.3f}\n"
                    f"   Preview: {preview}...\n"
                )
            
            return "\n".join(output_lines)
            
        except Exception as e:
            step_logger.error(f"[AgentTools] hybrid_vector_search error: {e}")
            return f"Search failed: {str(e)}"
    
    @tool
    def hybrid_keyword_search(words: List[str], top_k: int = 10) -> str:
        """
        Search for multiple keywords with connectivity-based reranking.
        
        Args:
            words: List of keywords to search for
            top_k: Maximum results per keyword (default: 10)
        """
        step_logger.info(f"[AgentTools] hybrid_keyword_search: {words}")
        
        try:
            all_results = {}
            
            # Search each keyword
            for word in words:
                results = graph_adapter.keyword_search(keywords=word, top_k=top_k)
                for r in results:
                    article_id = r.get("article_id")
                    if article_id not in all_results:
                        all_results[article_id] = r
                        all_results[article_id]["match_count"] = 1
                    else:
                        all_results[article_id]["match_count"] += 1
            
            if not all_results:
                return f"No articles found for keywords: {words}"
            
            # Compute connectivity and rerank
            results_list = list(all_results.values())
            for r in results_list:
                article_id = r.get("article_id")
                try:
                    in_refs = len(graph_adapter.get_referred_articles(article_id, max_refs=20))
                except:
                    in_refs = 0
                
                match_count = r.get("match_count", 1)
                r["connectivity_score"] = in_refs
                r["final_score"] = match_count + (in_refs * 0.1)
            
            results_list.sort(key=lambda x: x.get("final_score", 0), reverse=True)
            results_list = results_list[:top_k]
            
            output_lines = [f"Found {len(results_list)} articles matching {words}:\n"]
            for i, r in enumerate(results_list, 1):
                article_id = r.get("article_id", "unknown")
                context_accumulator.cache(article_id, r)
                
                preview = (r.get("article_text") or "")[:100]
                output_lines.append(
                    f"{i}. [{article_id}] {r.get('article_number', 'Article')} - "
                    f"{r.get('normativa_title', 'Unknown')[:40]}\n"
                    f"   Keywords matched: {r.get('match_count', 0)} | "
                    f"Connectivity: {r.get('connectivity_score', 0)}\n"
                    f"   Preview: {preview}...\n"
                )
            
            return "\n".join(output_lines)
            
        except Exception as e:
            step_logger.error(f"[AgentTools] hybrid_keyword_search error: {e}")
            return f"Search failed: {str(e)}"
    
    @tool
    def get_version_info(article_id: str) -> str:
        """
        Get version history of an article.
        
        Shows all versions of an article from oldest to newest,
        with effective dates and whether each version is current.
        
        Args:
            article_id: ID of any version of the article
        """
        step_logger.info(f"[AgentTools] get_version_info: {article_id}")
        
        try:
            versions = graph_adapter.get_all_next_versions(article_id)
            
            # Get the starting article info
            start_article = graph_adapter.get_article_by_id(article_id)
            if not start_article:
                return f"Article not found: {article_id}"
            
            output_lines = [
                f"Version history for {start_article.get('article_number', 'Article')}:\n",
                f"Starting version: {article_id}",
                f"  Effective: {start_article.get('fecha_vigencia', 'Unknown')}",
                f"  Expired: {start_article.get('fecha_caducidad', 'Current')}\n"
            ]
            
            if versions:
                output_lines.append(f"Found {len(versions)} subsequent version(s):\n")
                for i, v in enumerate(versions, 1):
                    is_current = not v.get("fecha_caducidad")
                    status = "✓ CURRENT" if is_current else "expired"
                    output_lines.append(
                        f"{i}. [{v.get('node_id')}] {status}\n"
                        f"   Effective: {v.get('fecha_vigencia', 'Unknown')}\n"
                    )
            else:
                output_lines.append("This is the only/latest version.")
            
            return "\n".join(output_lines)
            
        except Exception as e:
            step_logger.error(f"[AgentTools] get_version_info error: {e}")
            return f"Failed to get version info: {str(e)}"
    
    @tool
    def get_change_info(normativa_id: str) -> str:
        """
        Get modification history of a law (normativa).
        
        Shows which laws have modified this one, what articles were affected,
        and the type of changes (added, modified, removed).
        
        Args:
            normativa_id: ID of the law to check
        """
        step_logger.info(f"[AgentTools] get_change_info: {normativa_id}")
        
        try:
            from src.domain.repository.change_repository import ChangeRepository
            change_repo = ChangeRepository(graph_adapter)
            
            changes = change_repo.find_changes_for_document(normativa_id)
            
            if not changes:
                return f"No modification history found for: {normativa_id}"
            
            output_lines = [f"Modification history for {normativa_id}:\n"]
            
            for c in changes:
                source = c.get("source", "Unknown source")
                affected = c.get("affected_count", 0)
                change_details = c.get("changes", [])
                
                output_lines.append(f"Modified by: {source}")
                output_lines.append(f"  Affected articles: {affected}")
                
                if change_details:
                    added = [x for x in change_details if x.get("change_type") == "added"]
                    modified = [x for x in change_details if x.get("change_type") == "modified"]
                    removed = [x for x in change_details if x.get("change_type") == "removed"]
                    
                    if added:
                        output_lines.append(f"  + Added: {len(added)} articles")
                    if modified:
                        output_lines.append(f"  ~ Modified: {len(modified)} articles")
                    if removed:
                        output_lines.append(f"  - Removed: {len(removed)} articles")
                
                output_lines.append("")
            
            return "\n".join(output_lines)
            
        except Exception as e:
            step_logger.error(f"[AgentTools] get_change_info error: {e}")
            return f"Failed to get change info: {str(e)}"
    
    @tool
    def view_context() -> str:
        """
        View articles currently in the context.
        
        Shows all articles that have been added via add_to_context.
        Use this to review what will be used for the final answer.
        """
        step_logger.info("[AgentTools] view_context")
        
        chunks = context_accumulator.chunks
        
        if not chunks:
            return "Context is empty. Use add_to_context to add articles."
        
        output_lines = [f"Current context ({len(chunks)} articles):\n"]
        
        for i, chunk in enumerate(chunks, 1):
            article_id = chunk.get("article_id", "unknown")
            preview = (chunk.get("article_text") or chunk.get("full_text", ""))[:80]
            output_lines.append(
                f"{i}. [{article_id}] {chunk.get('article_number', 'Article')} - "
                f"{chunk.get('normativa_title', 'Unknown')[:30]}\n"
                f"   {preview}...\n"
            )
        
        return "\n".join(output_lines)
    
    @tool
    def remove_from_context(article_ids: List[str]) -> str:
        """
        Remove articles from the context.
        
        Use this to remove irrelevant articles before generating the final answer.
        
        Args:
            article_ids: List of article IDs to remove
        """
        step_logger.info(f"[AgentTools] remove_from_context: {article_ids}")
        
        removed = []
        not_found = []
        
        for article_id in article_ids:
            if article_id in context_accumulator._ids:
                context_accumulator._ids.discard(article_id)
                context_accumulator._chunks = [
                    c for c in context_accumulator._chunks 
                    if c.get("article_id") != article_id
                ]
                removed.append(article_id)
            else:
                not_found.append(article_id)
        
        parts = []
        if removed:
            parts.append(f"Removed {len(removed)} articles: {removed}")
        if not_found:
            parts.append(f"Not in context: {not_found}")
        
        result = ". ".join(parts) if parts else "No changes"
        result += f"\nRemaining articles in context: {len(context_accumulator.chunks)}"
        
        return result
    
    return [
        run_rag_query, 
        add_to_context,
        keyword_search,
        hybrid_vector_search,
        hybrid_keyword_search,
        get_version_info,
        get_change_info,
        view_context,
        remove_from_context
    ]

