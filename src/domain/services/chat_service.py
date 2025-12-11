"""
Chat Service.
Orchestrates the full chat flow: Query → RAG → Prompt → LLM → Citations → Response.
"""
import time
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from src.domain.interfaces.llm_provider import LLMProvider, Message
from src.domain.services.conversation_service import ConversationService
from src.domain.models.conversation import Conversation, ConversationMessage
from src.domain.models.citation import Citation
from src.ai.citations.citation_engine import CitationEngine
from src.ai.prompts.prompt_builder import PromptBuilder
from src.domain.interfaces.graph_adapter import GraphAdapter
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


class ChatService:
    """
    Main chat orchestration service.
    
    Flow:
    1. User sends query
    2. Retrieve relevant chunks from RAG (Neo4j vector search)
    3. Create citations from chunks
    4. Build prompt with context
    5. Generate response from LLM
    6. Extract used citations
    7. Return response with citations
    """
    
    def __init__(
        self,
        llm_provider: LLMProvider,
        graph_adapter: GraphAdapter,
        embedding_provider: EmbeddingProvider,
        conversation_service: ConversationService,
        citation_engine: Optional[CitationEngine] = None,
        prompt_builder: Optional[PromptBuilder] = None,
        retrieval_top_k: int = 5,
        index_name: str = "article_embeddings"
    ):
        """
        Initialize chat service with dependencies.
        
        Args:
            llm_provider: LLM provider for generation
            graph_adapter: Graph adapter for RAG retrieval (implements GraphAdapter)
            embedding_provider: Embedding provider for query embedding
            conversation_service: Service for managing conversations
            citation_engine: Engine for citation management (optional)
            prompt_builder: Builder for prompts (optional)
            retrieval_top_k: Number of chunks to retrieve
            index_name: Vector index name for search
        """
        self.llm_provider = llm_provider
        self.graph_adapter = graph_adapter
        self.embedding_provider = embedding_provider
        self.conversation_service = conversation_service
        self.citation_engine = citation_engine or CitationEngine()
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.retrieval_top_k = retrieval_top_k
        self.index_name = index_name
        
        step_logger.info(f"[ChatService] Initialized (top_k={retrieval_top_k})")
    
    def chat(
        self,
        query: str,
        conversation_id: Optional[str] = None,
        top_k: Optional[int] = None
    ) -> ChatResponse:
        """
        Process a chat query and return response with citations.
        
        Args:
            query: User's question
            conversation_id: Optional existing conversation ID
            top_k: Override for number of chunks to retrieve
            
        Returns:
            ChatResponse with answer and citations
        """
        start_time = time.time()
        
        step_logger.info(f"[ChatService] Processing query: '{query[:50]}...'")
        
        # Get or create conversation
        conversation = self.conversation_service.get_or_create_conversation(conversation_id)
        
        # Add user message to conversation
        conversation.add_user_message(query)
        
        # Step 1: Generate query embedding and retrieve from RAG
        retrieval_top_k = top_k or self.retrieval_top_k
        chunks = self._retrieve_chunks(query, retrieval_top_k)
        
        step_logger.info(f"[ChatService] Retrieved {len(chunks)} chunks")
        
        # Step 2: Create citations from chunks
        citations = self.citation_engine.create_citations(chunks)
        
        # Step 3: Build context from citations
        context = self.citation_engine.format_context_with_citations(citations)
        
        # Step 4: Build messages for LLM
        llm_messages = self._build_llm_messages(conversation, query)
        
        # Step 5: Generate response from LLM
        system_prompt = self.prompt_builder.build_system_prompt()
        
        try:
            llm_response = self.llm_provider.generate(
                messages=llm_messages,
                context=context,
                system_prompt=system_prompt
            )
            response_text = llm_response.content
        except Exception as e:
            step_logger.error(f"[ChatService] LLM generation failed: {e}")
            raise
        
        # Step 6: Extract, re-index citations, and rewrite response
        response_text, used_citations = self.citation_engine.extract_and_reindex_citations(
            response_text, citations
        )
        
        # Step 7: Add assistant message to conversation
        conversation.add_assistant_message(response_text, used_citations)
        
        execution_time_ms = (time.time() - start_time) * 1000
        
        step_logger.info(f"[ChatService] Response generated in {execution_time_ms:.2f}ms "
                        f"(citations used: {len(used_citations)})")
        
        return ChatResponse(
            response=response_text,
            conversation_id=conversation.id,
            citations=used_citations,
            execution_time_ms=execution_time_ms,
            metadata={
                "total_chunks_retrieved": len(chunks),
                "llm_model": self.llm_provider.model,
                "tokens_used": llm_response.usage if hasattr(llm_response, 'usage') else {}
            }
        )
    
    async def achat(
        self,
        query: str,
        conversation_id: Optional[str] = None,
        top_k: Optional[int] = None
    ) -> ChatResponse:
        """
        Async version of chat.
        
        Args:
            query: User's question
            conversation_id: Optional existing conversation ID
            top_k: Override for number of chunks to retrieve
            
        Returns:
            ChatResponse with answer and citations
        """
        start_time = time.time()
        
        step_logger.info(f"[ChatService] Processing async query: '{query[:50]}...'")
        
        # Get or create conversation
        conversation = self.conversation_service.get_or_create_conversation(conversation_id)
        
        # Add user message to conversation
        conversation.add_user_message(query)
        
        # Step 1: Retrieve from RAG (sync for now - Neo4j driver is sync)
        retrieval_top_k = top_k or self.retrieval_top_k
        chunks = self._retrieve_chunks(query, retrieval_top_k)
        
        # Step 2: Create citations
        citations = self.citation_engine.create_citations(chunks)
        
        # Step 3: Build context
        context = self.citation_engine.format_context_with_citations(citations)
        
        # Step 4: Build messages
        llm_messages = self._build_llm_messages(conversation, query)
        
        # Step 5: Generate response (async)
        system_prompt = self.prompt_builder.build_system_prompt()
        
        try:
            llm_response = await self.llm_provider.agenerate(
                messages=llm_messages,
                context=context,
                system_prompt=system_prompt
            )
            response_text = llm_response.content
        except Exception as e:
            step_logger.error(f"[ChatService] Async LLM generation failed: {e}")
            raise
        
        # Step 6: Extract, re-index citations, and rewrite response
        response_text, used_citations = self.citation_engine.extract_and_reindex_citations(
            response_text, citations
        )
        
        # Step 7: Add assistant message
        conversation.add_assistant_message(response_text, used_citations)
        
        execution_time_ms = (time.time() - start_time) * 1000
        
        return ChatResponse(
            response=response_text,
            conversation_id=conversation.id,
            citations=used_citations,
            execution_time_ms=execution_time_ms,
            metadata={
                "total_chunks_retrieved": len(chunks),
                "llm_model": self.llm_provider.model
            }
        )
    
    def _retrieve_chunks(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        """
        Retrieve relevant chunks from Neo4j using vector search.
        Augments results with version context when articles have next/previous versions.
        
        Args:
            query: User's query
            top_k: Number of chunks to retrieve
            
        Returns:
            List of article result dicts, augmented with version context
        """
        # Generate query embedding
        query_embedding = self.embedding_provider.get_embedding(query)
        
        # Perform vector search
        results = self.graph_adapter.vector_search(
            query_embedding=query_embedding,
            top_k=top_k,
            index_name=self.index_name
        )
        
        # Augment with version context
        augmented_results = self._augment_with_version_context(results)
        
        return augmented_results

    def _augment_with_version_context(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Augment retrieved chunks with version context as configured.
        
        For articles with next versions: recursively get all (or up to depth limit)
        For articles with previous versions: get immediate previous only (or up to depth limit)
        
        Args:
            chunks: List of article result dicts from vector search
            
        Returns:
            List of chunks with version_context field added where applicable
        """
        # Load config (cached after first load)
        import yaml
        try:
            with open("config/config.yaml", "r") as f:
                config = yaml.safe_load(f)
            version_config = config.get("version_context", {})
            next_depth = version_config.get("next_version_depth", -1)  # -1 = all
            prev_depth = version_config.get("previous_version_depth", 1)  # 1 = immediate only
        except Exception:
            # Fallback defaults if config not found
            next_depth = -1
            prev_depth = 1
        
        for chunk in chunks:
            version_context = []
            
            # Get next versions (recursively for newer versions)
            if chunk.get("next_version_id") is not None and next_depth != 0:
                next_versions = self._get_next_versions(chunk["article_id"], next_depth)
                if next_versions:
                    version_context.extend([
                        {
                            "type": "next",
                            "node_id": str(v.get("node_id", "")),
                            "article_number": v.get("article_number", ""),
                            "text": v.get("article_text", ""),
                            "fecha_vigencia": v.get("fecha_vigencia"),
                            "note": "Versión posterior"
                        }
                        for v in next_versions
                    ])
            
            # Get previous version (limited depth for historical context)
            if chunk.get("previous_version_id") is not None and prev_depth > 0:
                prev_version = self.graph_adapter.get_previous_version(chunk["article_id"])
                if prev_version:
                    version_context.append({
                        "type": "previous",
                        "node_id": str(prev_version.get("node_id", "")),
                        "article_number": prev_version.get("article_number", ""),
                        "text": prev_version.get("article_text", ""),
                        "fecha_vigencia": prev_version.get("fecha_vigencia"),
                        "note": "Versión anterior"
                    })
            
            # Add version context to chunk
            if version_context:
                chunk["version_context"] = version_context
                step_logger.info(f"[ChatService] Added {len(version_context)} version(s) context to article {chunk.get('article_id')}")
        
        return chunks

    def _get_next_versions(self, node_id: str, max_depth: int = -1) -> List[Dict[str, Any]]:
        """
        Get all next versions of an article up to max_depth.
        
        Args:
            node_id: ID of the starting article node
            max_depth: Maximum depth to traverse (-1 = unlimited)
            
        Returns:
            List of version data
        """
        all_versions = self.graph_adapter.get_all_next_versions(node_id)
        
        if max_depth == -1:
            return all_versions
        else:
            return all_versions[:max_depth]
    
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
        
        # Get conversation history (excluding the just-added user message)
        history = self.conversation_service.get_context_messages(conversation)
        
        # Convert to LLM Message format (skip the last message which is current query)
        for conv_msg in history[:-1]:
            messages.append(Message(
                role=conv_msg.role,
                content=conv_msg.content,
                timestamp=conv_msg.timestamp
            ))
        
        # Add current query
        messages.append(Message(role="user", content=current_query))
        
        return messages
