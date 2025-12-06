"""
Conversation Service.
Manages multi-turn conversations with context retention.
"""
from typing import Dict, Optional, List
from datetime import datetime, timedelta

from src.domain.models.conversation import Conversation, ConversationMessage
from src.domain.models.citation import Citation
from src.utils.logger import step_logger


class ConversationService:
    """
    Service for managing chat conversations.
    
    Features:
    - Create and retrieve conversations
    - Add messages with citations
    - Manage conversation context for LLM
    - In-memory storage (can be extended to persistent storage)
    """
    
    def __init__(
        self, 
        max_history_messages: int = 10,
        conversation_ttl_hours: int = 24
    ):
        """
        Initialize conversation service.
        
        Args:
            max_history_messages: Max messages to retain for context
            conversation_ttl_hours: Hours before conversations expire
        """
        self.max_history_messages = max_history_messages
        self.conversation_ttl = timedelta(hours=conversation_ttl_hours)
        
        # In-memory storage (could be replaced with Redis, DB, etc.)
        self._conversations: Dict[str, Conversation] = {}
        
        step_logger.info(f"[ConversationService] Initialized (max_history={max_history_messages})")
    
    def create_conversation(self) -> Conversation:
        """
        Create a new conversation.
        
        Returns:
            New Conversation instance
        """
        conversation = Conversation()
        self._conversations[conversation.id] = conversation
        
        step_logger.info(f"[ConversationService] Created conversation: {conversation.id}")
        
        return conversation
    
    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """
        Retrieve a conversation by ID.
        
        Args:
            conversation_id: Unique conversation identifier
            
        Returns:
            Conversation if found and not expired, None otherwise
        """
        conversation = self._conversations.get(conversation_id)
        
        if conversation:
            # Check if expired
            if datetime.now() - conversation.updated_at > self.conversation_ttl:
                step_logger.info(f"[ConversationService] Conversation expired: {conversation_id}")
                del self._conversations[conversation_id]
                return None
        
        return conversation
    
    def get_or_create_conversation(self, conversation_id: Optional[str] = None) -> Conversation:
        """
        Get existing conversation or create new one.
        
        Args:
            conversation_id: Optional ID of existing conversation
            
        Returns:
            Conversation instance
        """
        if conversation_id:
            conversation = self.get_conversation(conversation_id)
            if conversation:
                return conversation
        
        return self.create_conversation()
    
    def add_user_message(
        self, 
        conversation_id: str, 
        content: str
    ) -> Optional[ConversationMessage]:
        """
        Add a user message to a conversation.
        
        Args:
            conversation_id: Conversation ID
            content: Message content
            
        Returns:
            Created message, or None if conversation not found
        """
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            return None
        
        return conversation.add_user_message(content)
    
    def add_assistant_message(
        self, 
        conversation_id: str, 
        content: str,
        citations: Optional[List[Citation]] = None
    ) -> Optional[ConversationMessage]:
        """
        Add an assistant message to a conversation.
        
        Args:
            conversation_id: Conversation ID
            content: Message content
            citations: Optional list of citations
            
        Returns:
            Created message, or None if conversation not found
        """
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            return None
        
        return conversation.add_assistant_message(content, citations)
    
    def get_context_messages(
        self, 
        conversation: Conversation
    ) -> List[ConversationMessage]:
        """
        Get messages for LLM context, respecting max history limit.
        
        Args:
            conversation: Conversation to get context from
            
        Returns:
            List of recent messages for context
        """
        return conversation.get_history(max_messages=self.max_history_messages)
    
    def clear_conversation(self, conversation_id: str) -> bool:
        """
        Clear all messages from a conversation.
        
        Args:
            conversation_id: Conversation to clear
            
        Returns:
            True if conversation was found and cleared
        """
        conversation = self.get_conversation(conversation_id)
        if conversation:
            conversation.clear()
            step_logger.info(f"[ConversationService] Cleared conversation: {conversation_id}")
            return True
        return False
    
    def delete_conversation(self, conversation_id: str) -> bool:
        """
        Delete a conversation entirely.
        
        Args:
            conversation_id: Conversation to delete
            
        Returns:
            True if conversation was found and deleted
        """
        if conversation_id in self._conversations:
            del self._conversations[conversation_id]
            step_logger.info(f"[ConversationService] Deleted conversation: {conversation_id}")
            return True
        return False
    
    def cleanup_expired(self) -> int:
        """
        Remove expired conversations.
        
        Returns:
            Number of conversations removed
        """
        now = datetime.now()
        expired_ids = [
            cid for cid, conv in self._conversations.items()
            if now - conv.updated_at > self.conversation_ttl
        ]
        
        for cid in expired_ids:
            del self._conversations[cid]
        
        if expired_ids:
            step_logger.info(f"[ConversationService] Cleaned up {len(expired_ids)} expired conversations")
        
        return len(expired_ids)
