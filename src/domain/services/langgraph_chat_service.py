"""
LangGraph-based Chat Service.
Uses a LangGraph StateGraph for workflow orchestration.
Supports both in-memory and SQLite-backed conversation persistence.
"""
import time
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from src.domain.interfaces.llm_provider import LLMProvider, Message
from src.domain.interfaces.context_collector import ContextCollector
from src.domain.models.conversation import Conversation
from src.domain.models.citation import Citation
from src.ai.citations.citation_engine import CitationEngine
from src.ai.prompts.prompt_builder import PromptBuilder
from src.ai.graph.workflow import build_chat_workflow
from src.ai.context_collectors import RAGCollector
from src.infrastructure.graphdb.adapter import Neo4jAdapter
from src.domain.interfaces.embedding_provider import EmbeddingProvider
from src.utils.logger import step_logger


@dataclass
class ChatResponse:
    """Response from chat service."""
    response: str
    conversation_id: str
    citations: List[Citation]
    execution_time_ms: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "response": self.response,
            "conversation_id": self.conversation_id,
            "citations": [c.to_summary_dict() for c in self.citations],
            "execution_time_ms": self.execution_time_ms,
            "metadata": self.metadata
        }


class LangGraphChatService:
    """
    Chat service using LangGraph for workflow orchestration.
    
    Supports two modes:
    1. In-memory (legacy): Uses ConversationService for session storage
    2. SQLite-backed: Uses ConversationRepository for persistent storage
    
    The workflow graph handles the context collection pipeline:
    
    Flow:
    1. collect_context - Gather relevant context via ContextCollector
    2. build_citations - Create citations from chunks
    3. generate - Generate LLM response with context
    4. extract_citations - Extract used citations from response
    
    The ContextCollector can be swapped for different strategies:
    - RAGContextCollector (default): Vector search using embeddings
    - Future: GraphContextCollector, HybridContextCollector, VoyagerContextCollector, etc.
    """
    
    def __init__(
        self,
        llm_provider: LLMProvider,
        # Context collector can be injected or auto-created from adapter/embedding provider
        context_collector: Optional[ContextCollector] = None,
        neo4j_adapter: Optional[Neo4jAdapter] = None,
        embedding_provider: Optional[EmbeddingProvider] = None,
        # Can accept either ConversationService (in-memory) or ConversationRepository (SQLite)
        conversation_service=None,
        conversation_repository=None,
        citation_engine: Optional[CitationEngine] = None,
        prompt_builder: Optional[PromptBuilder] = None,
        retrieval_top_k: int = 5,
        index_name: str = "article_embeddings",
        checkpointer=None
    ):
        """
        Initialize LangGraph chat service with dependencies.
        
        Args:
            llm_provider: LLM provider for generation
            context_collector: ContextCollector for gathering context (recommended)
            neo4j_adapter: Neo4j adapter (optional, used to create default RAGContextCollector)
            embedding_provider: Embedding provider (optional, used to create default RAGContextCollector)
            conversation_service: In-memory conversation service (legacy)
            conversation_repository: SQLite conversation repository (new)
            citation_engine: Engine for citation management (optional)
            prompt_builder: Builder for prompts (optional)
            retrieval_top_k: Number of chunks to retrieve
            index_name: Vector index name for search
            checkpointer: Optional SQLite checkpointer for graph state persistence
            
        Note:
            Either provide a context_collector directly, or provide both
            neo4j_adapter and embedding_provider to auto-create a RAGCollector.
        """
        self.llm_provider = llm_provider
        self.conversation_service = conversation_service
        self.conversation_repository = conversation_repository
        self.citation_engine = citation_engine or CitationEngine()
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.retrieval_top_k = retrieval_top_k
        self.checkpointer = checkpointer
        
        # Create or use provided context collector
        if context_collector:
            self.context_collector = context_collector
        elif neo4j_adapter and embedding_provider:
            # Backward compatibility: create RAGCollector from components
            self.context_collector = RAGCollector(
                neo4j_adapter=neo4j_adapter,
                embedding_provider=embedding_provider,
                index_name=index_name
            )
        else:
            raise ValueError(
                "Either provide a context_collector, or both neo4j_adapter and embedding_provider"
            )
        
        # Determine persistence mode
        self.use_sqlite = conversation_repository is not None
        
        # Build the LangGraph workflow with context collector
        self.workflow = build_chat_workflow(
            context_collector=self.context_collector,
            llm_provider=llm_provider,
            citation_engine=self.citation_engine,
            prompt_builder=self.prompt_builder,
            checkpointer=checkpointer
        )
        
        mode = "SQLite" if self.use_sqlite else "in-memory"
        step_logger.info(f"[LangGraphChatService] Initialized with {mode} persistence, "
                         f"collector={self.context_collector.name} (top_k={retrieval_top_k})")
    
    def chat(
        self,
        query: str,
        conversation_id: Optional[str] = None,
        top_k: Optional[int] = None,
        user_id: Optional[str] = None
    ) -> ChatResponse:
        """
        Process a chat query using LangGraph workflow.
        
        Args:
            query: User's question
            conversation_id: Optional existing conversation ID
            top_k: Override for number of chunks to retrieve
            user_id: User ID for SQLite mode (required for persistence)
            
        Returns:
            ChatResponse with answer and citations
        """
        start_time = time.time()
        
        step_logger.info(f"[LangGraphChatService] Processing query: '{query[:50]}...'")
        
        # Get or create conversation based on persistence mode
        if self.use_sqlite:
            conversation = self._get_or_create_conversation_sqlite(conversation_id, user_id)
        else:
            conversation = self._get_or_create_conversation_memory(conversation_id)
        
        # Add user message to conversation
        self._add_user_message(conversation, query, user_id)
        
        # Build messages from conversation history
        messages = self._build_llm_messages(conversation, query)
        step_logger.info(f"[LangGraphChatService] Built {len(messages)} messages for LLM context")
        
        # Prepare initial state for the workflow
        initial_state = {
            "query": query,
            "conversation_id": conversation.id,
            "top_k": top_k or self.retrieval_top_k,
            "chunks": [],
            "context_strategy": "",  # Will be set by collect_context_node
            "citations": [],
            "context": "",
            "messages": messages,
            "system_prompt": "",
            "response": "",
            "used_citations": [],
            "start_time": start_time,
            "execution_time_ms": 0.0,
            "metadata": {}
        }
        
        # Execute the LangGraph workflow
        # Pass thread_id in config for checkpointing
        step_logger.info(f"[LangGraphChatService] Invoking workflow...")
        
        if self.checkpointer:
            # Use thread_id for LangGraph checkpointing
            config = {"configurable": {"thread_id": conversation.id}}
            result = self.workflow.invoke(initial_state, config=config)
        else:
            result = self.workflow.invoke(initial_state)
        
        # Add assistant message to conversation
        self._add_assistant_message(conversation, result["response"], result["used_citations"], user_id)
        
        step_logger.info(f"[LangGraphChatService] Completed in {result['execution_time_ms']:.2f}ms "
                        f"(citations used: {len(result['used_citations'])})")
        
        return ChatResponse(
            response=result["response"],
            conversation_id=conversation.id,
            citations=result["used_citations"],
            execution_time_ms=result["execution_time_ms"],
            metadata={
                "total_chunks_retrieved": len(result["chunks"]),
                "workflow": "langgraph",
                "persistence": "sqlite" if self.use_sqlite else "memory",
                **result.get("metadata", {})
            }
        )
    
    async def achat(
        self,
        query: str,
        conversation_id: Optional[str] = None,
        top_k: Optional[int] = None,
        user_id: Optional[str] = None
    ) -> ChatResponse:
        """
        Async version of chat.
        
        Note: Currently wraps sync call for compatibility.
        LangGraph async support can be added later.
        
        Args:
            query: User's question
            conversation_id: Optional existing conversation ID
            top_k: Override for number of chunks to retrieve
            user_id: User ID for SQLite mode (required for persistence)
            
        Returns:
            ChatResponse with answer and citations
        """
        return self.chat(query, conversation_id, top_k, user_id)
    
    def _get_or_create_conversation_sqlite(
        self, 
        conversation_id: Optional[str],
        user_id: str
    ) -> Conversation:
        """Get or create conversation using SQLite repository."""
        if conversation_id:
            conversation = self.conversation_repository.get_conversation_unchecked(conversation_id)
            if conversation:
                return conversation
        
        # Create new conversation
        return self.conversation_repository.create_conversation(user_id)
    
    def _get_or_create_conversation_memory(
        self,
        conversation_id: Optional[str]
    ) -> Conversation:
        """Get or create conversation using in-memory service."""
        return self.conversation_service.get_or_create_conversation(conversation_id)
    
    def _add_user_message(
        self,
        conversation: Conversation,
        content: str,
        user_id: Optional[str] = None
    ):
        """Add user message to conversation."""
        if self.use_sqlite:
            self.conversation_repository.add_message(conversation.id, "user", content)
        else:
            conversation.add_user_message(content)
    
    def _add_assistant_message(
        self,
        conversation: Conversation,
        content: str,
        citations: List[Citation],
        user_id: Optional[str] = None
    ):
        """Add assistant message to conversation."""
        if self.use_sqlite:
            self.conversation_repository.add_message(
                conversation.id, "assistant", content, citations
            )
        else:
            conversation.add_assistant_message(content, citations)
    
    def _build_llm_messages(
        self, 
        conversation: Conversation,
        current_query: str
    ) -> List[Message]:
        """
        Build message list for LLM from conversation history.
        
        Args:
            conversation: Current conversation
            current_query: The current user query
            
        Returns:
            List of Message objects for LLM
        """
        messages = []
        
        # Get conversation history
        if self.use_sqlite:
            # Reload conversation from database to get all messages (including just-added user message)
            # This ensures we have the full history after server restart
            reloaded = self.conversation_repository.get_conversation_unchecked(conversation.id)
            history = reloaded.messages if reloaded else []
        else:
            # Get from in-memory service
            history = self.conversation_service.get_context_messages(conversation)
        
        # Convert to LLM Message format (skip the last message which is current query already added)
        for conv_msg in history[:-1] if history else []:
            messages.append(Message(
                role=conv_msg.role,
                content=conv_msg.content,
                timestamp=conv_msg.timestamp
            ))
        
        # Add current query
        messages.append(Message(role="user", content=current_query))
        
        return messages
    
    async def achat_stream(
        self,
        query: str,
        conversation_id: Optional[str] = None,
        top_k: Optional[int] = None,
        user_id: Optional[str] = None
    ):
        """
        Stream chat response with chunks, citations, and completion events.
        
        This method performs context collection synchronously, then streams
        the LLM response. Citations are extracted and sent after streaming completes.
        
        Args:
            query: User's question
            conversation_id: Optional existing conversation ID
            top_k: Override for number of chunks to retrieve
            user_id: User ID for SQLite mode (required for persistence)
            
        Yields:
            dict: Event objects with types:
                - {"type": "chunk", "content": "..."}
                - {"type": "citations", "citations": [...]}
                - {"type": "done", "conversation_id": "...", "execution_time_ms": ...}
        """
        import time
        start_time = time.time()
        
        step_logger.info(f"[LangGraphChatService] Starting streaming for query: '{query[:50]}...'")
        
        # Get or create conversation based on persistence mode
        if self.use_sqlite:
            conversation = self._get_or_create_conversation_sqlite(conversation_id, user_id)
        else:
            conversation = self._get_or_create_conversation_memory(conversation_id)
        
        # Add user message to conversation
        self._add_user_message(conversation, query, user_id)
        
        # Build messages from conversation history
        messages = self._build_llm_messages(conversation, query)
        step_logger.info(f"[LangGraphChatService] Built {len(messages)} messages for LLM context")
        
        # Step 1: Collect context (non-streaming, we need it before generation)
        step_logger.info(f"[LangGraphChatService] Collecting context...")
        context_result = self.context_collector.collect(
            query=query,
            top_k=top_k or self.retrieval_top_k
        )
        
        # Step 2: Build citations
        citations = self.citation_engine.create_citations(context_result.chunks)
        context = self.citation_engine.format_context_with_citations(citations)
        step_logger.info(f"[LangGraphChatService] Created {len(citations)} citations")
        
        # Step 3: Build system prompt
        system_prompt = self.prompt_builder.build_system_prompt()
        
        # Step 4: Stream LLM response
        step_logger.info(f"[LangGraphChatService] Starting LLM streaming...")
        full_response = []
        final_llm_response = None
        
        try:
            async for item in self.llm_provider.agenerate_stream(
                messages=messages,
                context=context,
                system_prompt=system_prompt
            ):
                if isinstance(item, dict) and "_final_response" in item:
                    # Final response marker
                    final_llm_response = item["_final_response"]
                else:
                    # Text chunk
                    full_response.append(item)
                    yield {"type": "chunk", "content": item}
        except Exception as e:
            step_logger.error(f"[LangGraphChatService] Streaming error: {e}")
            yield {"type": "error", "message": str(e)}
            return
        
        # Step 5: Extract and re-index citations from complete response
        response_text = "".join(full_response)
        cleaned_response, used_citations = self.citation_engine.extract_and_reindex_citations(
            response_text, citations
        )
        
        # Step 6: Add assistant message to conversation
        self._add_assistant_message(conversation, cleaned_response, used_citations, user_id)
        
        execution_time_ms = (time.time() - start_time) * 1000
        
        step_logger.info(f"[LangGraphChatService] Streaming completed in {execution_time_ms:.2f}ms "
                        f"(citations used: {len(used_citations)})")
        
        # Yield citations
        citation_dicts = [c.to_summary_dict() for c in used_citations]
        yield {"type": "citations", "citations": citation_dicts}
        
        # Yield done event with metadata
        yield {
            "type": "done",
            "conversation_id": conversation.id,
            "execution_time_ms": execution_time_ms,
            "metadata": {
                "total_chunks_retrieved": len(context_result.chunks),
                "workflow": "streaming",
                "persistence": "sqlite" if self.use_sqlite else "memory"
            }
        }

