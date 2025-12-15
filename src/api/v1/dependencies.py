"""
FastAPI dependencies for dependency injection.
Manages Neo4j connections, embedding providers, LLM providers, and chat services.
"""
import os
from typing import Generator, Optional
from functools import lru_cache

from dotenv import load_dotenv
from src.infrastructure.graphdb.connection import Neo4jConnection
from src.infrastructure.graphdb.adapter import Neo4jAdapter
from src.ai.embeddings.factory import EmbeddingFactory
from src.domain.interfaces.embedding_provider import EmbeddingProvider
from src.domain.value_objects.embedding_config import EmbeddingConfig
from src.utils.logger import step_logger

# Load environment variables
load_dotenv()


class AppConfig:
    """Application configuration from environment variables."""
    
    def __init__(self):
        self.neo4j_uri = os.getenv("NEO4J_URI")
        self.neo4j_user = os.getenv("NEO4J_USER")
        self.neo4j_password = os.getenv("NEO4J_PASSWORD")
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        
        # Embedding configuration
        self.embedding_model = "models/gemini-embedding-001"
        self.embedding_dimensions = 768
        self.embedding_task_type = "RETRIEVAL_QUERY"  # For queries, not documents
        
        # LLM configuration (from env or defaults)
        self.llm_provider = os.getenv("LLM_PROVIDER", "gemini")
        self.llm_model = os.getenv("LLM_MODEL", "gemini-2.5-flash")
        self.llm_temperature = float(os.getenv("LLM_TEMPERATURE", "0.3"))
        self.llm_max_tokens = int(os.getenv("LLM_MAX_TOKENS", "1024"))
        
        # Retrieval configuration
        self.retrieval_top_k = int(os.getenv("RETRIEVAL_TOP_K", "5"))
        self.retrieval_index_name = os.getenv("RETRIEVAL_INDEX_NAME", "article_embeddings")
        
        # Conversation configuration
        self.max_history_messages = int(os.getenv("MAX_HISTORY_MESSAGES", "10"))
        self.conversation_ttl_hours = int(os.getenv("CONVERSATION_TTL_HOURS", "24"))
        
        # Validate required config
        if not all([self.neo4j_uri, self.neo4j_user, self.neo4j_password]):
            raise ValueError("Missing required Neo4j configuration in environment variables")
        
        if not self.google_api_key:
            raise ValueError("Missing GOOGLE_API_KEY in environment variables")


@lru_cache()
def get_config() -> AppConfig:
    """
    Get application configuration (cached singleton).
    
    Returns:
        AppConfig instance
    """
    return AppConfig()


def get_neo4j_connection() -> Generator[Neo4jConnection, None, None]:
    """
    Dependency that provides Neo4j connection.
    Creates a new connection for each request and closes it when done.
    
    Yields:
        Neo4jConnection instance
    """
    config = get_config()
    connection = Neo4jConnection(
        uri=config.neo4j_uri,
        user=config.neo4j_user,
        password=config.neo4j_password
    )
    try:
        yield connection
    finally:
        connection.close()


def get_neo4j_adapter(
    connection: Neo4jConnection = None
) -> Neo4jAdapter:
    """
    Dependency that provides Neo4j adapter.
    
    Args:
        connection: Neo4j connection (injected by FastAPI)
    
    Returns:
        Neo4jAdapter instance
    """
    if connection is None:
        # Fallback for manual usage
        config = get_config()
        connection = Neo4jConnection(
            uri=config.neo4j_uri,
            user=config.neo4j_user,
            password=config.neo4j_password
        )
    
    return Neo4jAdapter(connection)


@lru_cache()
def get_embedding_provider() -> EmbeddingProvider:
    """
    Dependency that provides embedding provider (cached singleton).
    Uses Gemini embeddings optimized for query retrieval.
    
    Returns:
        EmbeddingProvider instance
    """
    config = get_config()
    
    embedding_provider = EmbeddingFactory.create(
        provider="gemini",
        model=config.embedding_model,
        dimensions=config.embedding_dimensions,
        task_type=config.embedding_task_type
    )
    
    return embedding_provider


# ========== Chat-related Dependencies ==========

# Lazy imports for chat components
_llm_provider = None
_conversation_service = None
_chroma_store = None


def get_llm_provider():
    """
    Dependency that provides LLM provider (cached singleton).
    
    Uses ResilientLLMProvider (with fallback) if llm.resilient.enabled=true in config.
    Otherwise falls back to direct LLMFactory with LLM_PROVIDER env var.
    
    Returns:
        LLMProvider instance (ResilientLLMProvider or direct provider)
    """
    global _llm_provider
    
    if _llm_provider is None:
        # Try ResilientLLMProvider first (Main → Backup → Fallback)
        try:
            from src.ai.llm.resilient_provider import ResilientLLMProvider
            _llm_provider = ResilientLLMProvider()
            step_logger.info("[Dependencies] Using ResilientLLMProvider with fallback chain")
        except ValueError as e:
            # ResilientLLMProvider requires config - fall back to direct factory
            step_logger.info(f"[Dependencies] ResilientLLMProvider not enabled, using direct factory: {e}")
            from src.ai.llm.factory import LLMFactory
            config = get_config()
            
            _llm_provider = LLMFactory.create(
                provider=config.llm_provider,
                model=config.llm_model,
                temperature=config.llm_temperature,
                max_tokens=config.llm_max_tokens
            )
    
    return _llm_provider


def get_conversation_service():
    """
    Dependency that provides conversation service (cached singleton).
    
    Returns:
        ConversationService instance
    """
    global _conversation_service
    
    if _conversation_service is None:
        from src.domain.services.conversation_service import ConversationService
        config = get_config()
        
        _conversation_service = ConversationService(
            max_history_messages=config.max_history_messages,
            conversation_ttl_hours=config.conversation_ttl_hours
        )
    
    return _conversation_service


def get_chroma_store():
    """
    Dependency that provides ChromaDB classification store (cached singleton).
    Used for context decision embedding similarity.
    
    Returns:
        ChromaClassificationStore instance (seeded with default phrases)
    """
    global _chroma_store
    
    if _chroma_store is None:
        from src.infrastructure.chroma import ChromaClassificationStore
        
        _chroma_store = ChromaClassificationStore(
            persist_directory="data/chroma",
            embedding_provider=get_embedding_provider(),
            cache_path="data/classification_embeddings_cache.json"
        )
        
        # Seed with defaults if not already seeded
        _chroma_store.seed_defaults()
        
        step_logger.info("[Dependencies] ChromaDB classification store initialized and seeded")
    
    return _chroma_store


from fastapi import Depends

# ... (rest of imports)

# ... (previous code)

def get_chat_service(
    connection: Neo4jConnection = Depends(get_neo4j_connection)
):
    """
    Dependency that provides chat service.
    Creates a new instance per request with shared singletons.
    
    Uses LangGraph-based service if USE_LANGGRAPH=true env var is set (default).
    Set USE_LANGGRAPH=false to use the original ChatService.
    
    Args:
        connection: Neo4j connection (injected by FastAPI)
    
    Returns:
        ChatService or LangGraphChatService instance
    """
    use_langgraph = os.getenv("USE_LANGGRAPH", "true").lower() == "true"
    
    if use_langgraph:
        from src.domain.services.langgraph_chat_service import LangGraphChatService as ChatService
    else:
        from src.domain.services.chat_service import ChatService
    
    from src.ai.citations.citation_engine import CitationEngine
    from src.ai.prompts.prompt_builder import PromptBuilder
    
    config = get_config()
    adapter = Neo4jAdapter(connection)
    
    return ChatService(
        llm_provider=get_llm_provider(),
        neo4j_adapter=adapter,
        embedding_provider=get_embedding_provider(),
        conversation_service=get_conversation_service(),
        citation_engine=CitationEngine(),
        prompt_builder=PromptBuilder(),
        retrieval_top_k=config.retrieval_top_k,
        index_name=config.retrieval_index_name
    )


def get_context_collector(
    collector_type: str = "rag",
    neo4j_adapter: Neo4jAdapter = None,
    embedding_provider = None,
    llm_provider = None,
    index_name: str = "article_embeddings"
):
    """
    Factory function to create context collectors based on type.
    
    Args:
        collector_type: Type of collector ("rag" or "qrag")
        neo4j_adapter: Neo4j adapter instance
        embedding_provider: Embedding provider instance
        llm_provider: LLM provider (required for qrag)
        index_name: Vector index name
        
    Returns:
        ContextCollector instance
    """
    from src.ai.context_collectors import RAGCollector, QRAGCollector
    
    if collector_type == "qrag":
        if not llm_provider:
            llm_provider = get_llm_provider()
        return QRAGCollector(
            neo4j_adapter=neo4j_adapter,
            embedding_provider=embedding_provider,
            llm_provider=llm_provider,
            index_name=index_name
        )
    else:
        return RAGCollector(
            neo4j_adapter=neo4j_adapter,
            embedding_provider=embedding_provider,
            index_name=index_name
        )


def get_chat_service_with_collector(
    connection: Neo4jConnection = Depends(get_neo4j_connection),
    collector_type: str = "rag"
):
    """
    Dependency that provides chat service with specified collector type.
    Creates a new instance per request with SQLite conversation repository.
    
    Args:
        connection: Neo4j connection (injected by FastAPI)
        collector_type: Context collector type ("rag" or "qrag")
    
    Returns:
        LangGraphChatService instance with specified collector
    """
    from src.domain.services.langgraph_chat_service import LangGraphChatService
    from src.ai.citations.citation_engine import CitationEngine
    from src.ai.prompts.prompt_builder import PromptBuilder
    from src.infrastructure.database import get_database_connection
    from src.infrastructure.database.repository_factory import get_conversation_repository
    from src.infrastructure.database.checkpointer import get_checkpointer
    
    config = get_config()
    adapter = Neo4jAdapter(connection)
    
    # Get database connection and repositories (uses MariaDB or SQLite based on config)
    db_conn = get_database_connection()
    conversation_repo = get_conversation_repository(db_conn)
    
    # Get checkpointer for LangGraph state persistence (MariaDB or SQLite)
    checkpointer = get_checkpointer()
    
    # Create the appropriate context collector
    context_collector = get_context_collector(
        collector_type=collector_type,
        neo4j_adapter=adapter,
        embedding_provider=get_embedding_provider(),
        llm_provider=get_llm_provider(),
        index_name=config.retrieval_index_name
    )
    
    chat_service = LangGraphChatService(
        llm_provider=get_llm_provider(),
        context_collector=context_collector,
        conversation_repository=conversation_repo,
        citation_engine=CitationEngine(),
        prompt_builder=PromptBuilder(),
        retrieval_top_k=config.retrieval_top_k,
        checkpointer=checkpointer
    )
    
    # Enable context decision with ChromaDB embedding similarity
    chat_service.set_chroma_store(get_chroma_store())
    
    return chat_service


def get_chat_service_with_user(
    connection: Neo4jConnection = Depends(get_neo4j_connection)
):
    """
    Dependency that provides chat service with SQLite-backed persistence.
    Creates a new instance per request with SQLite conversation repository.
    
    Uses LangGraph-based service with SQLite checkpointing for graph state persistence.
    
    Args:
        connection: Neo4j connection (injected by FastAPI)
    
    Returns:
        LangGraphChatService instance with SQLite persistence
    """
    from src.domain.services.langgraph_chat_service import LangGraphChatService
    from src.ai.citations.citation_engine import CitationEngine
    from src.ai.prompts.prompt_builder import PromptBuilder
    from src.infrastructure.database import get_database_connection
    from src.infrastructure.database.repository_factory import get_conversation_repository
    from src.infrastructure.database.checkpointer import get_checkpointer
    
    config = get_config()
    adapter = Neo4jAdapter(connection)
    
    # Get database connection and repositories (uses MariaDB or SQLite based on config)
    db_conn = get_database_connection()
    conversation_repo = get_conversation_repository(db_conn)
    
    # Get checkpointer for LangGraph state persistence (MariaDB or SQLite)
    checkpointer = get_checkpointer()
    
    chat_service = LangGraphChatService(
        llm_provider=get_llm_provider(),
        neo4j_adapter=adapter,
        embedding_provider=get_embedding_provider(),
        conversation_repository=conversation_repo,
        citation_engine=CitationEngine(),
        prompt_builder=PromptBuilder(),
        retrieval_top_k=config.retrieval_top_k,
        index_name=config.retrieval_index_name,
        checkpointer=checkpointer
    )
    
    # Enable context decision with ChromaDB embedding similarity
    chat_service.set_chroma_store(get_chroma_store())
    
    return chat_service
