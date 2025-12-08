"""
Conversation repository for SQLite persistence.
Handles conversation and message CRUD with user isolation.
"""
import json
from datetime import datetime
from typing import Optional, List
import uuid

from src.infrastructure.sqlite.connection import SQLiteConnection
from src.domain.models.conversation import Conversation, ConversationMessage
from src.domain.models.citation import Citation
from src.utils.logger import step_logger


class ConversationRepository:
    """
    Repository for conversation persistence in SQLite.
    
    Provides methods for creating, retrieving, and managing conversations
    with proper user isolation.
    """
    
    def __init__(self, connection: SQLiteConnection):
        """
        Initialize repository with connection manager.
        
        Args:
            connection: SQLite connection manager
        """
        self.connection = connection
    
    def create_conversation(self, user_id: str) -> Conversation:
        """
        Create a new conversation for a user.
        
        Args:
            user_id: Owner user ID
            
        Returns:
            Created Conversation
        """
        conversation = Conversation()
        now = datetime.now()
        
        self.connection.execute(
            """
            INSERT INTO conversations (id, user_id, created_at, updated_at, metadata)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                conversation.id,
                user_id,
                now.isoformat(),
                now.isoformat(),
                json.dumps(conversation.metadata)
            )
        )
        
        step_logger.info(f"[ConvRepo] Created conversation: {conversation.id} for user: {user_id}")
        return conversation
    
    def get_conversation(
        self, 
        conversation_id: str, 
        user_id: str
    ) -> Optional[Conversation]:
        """
        Get conversation by ID (with user ownership check).
        
        Args:
            conversation_id: Conversation ID
            user_id: User ID (for ownership verification)
            
        Returns:
            Conversation or None if not found/not owned
        """
        # Get conversation
        row = self.connection.fetchone(
            "SELECT * FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id)
        )
        
        if row is None:
            return None
        
        # Build conversation
        conversation = Conversation(
            id=row['id'],
            messages=[],
            created_at=datetime.fromisoformat(row['created_at']),
            updated_at=datetime.fromisoformat(row['updated_at']),
            metadata=json.loads(row['metadata']) if row['metadata'] else {}
        )
        
        # Load messages
        self._load_messages(conversation)
        
        return conversation
    
    def get_conversation_unchecked(self, conversation_id: str) -> Optional[Conversation]:
        """
        Get conversation by ID without user check (internal use).
        
        Args:
            conversation_id: Conversation ID
            
        Returns:
            Conversation or None if not found
        """
        row = self.connection.fetchone(
            "SELECT * FROM conversations WHERE id = ?",
            (conversation_id,)
        )
        
        if row is None:
            return None
        
        conversation = Conversation(
            id=row['id'],
            messages=[],
            created_at=datetime.fromisoformat(row['created_at']),
            updated_at=datetime.fromisoformat(row['updated_at']),
            metadata=json.loads(row['metadata']) if row['metadata'] else {}
        )
        
        self._load_messages(conversation)
        return conversation
    
    def get_conversation_user_id(self, conversation_id: str) -> Optional[str]:
        """
        Get the user ID that owns a conversation.
        
        Args:
            conversation_id: Conversation ID
            
        Returns:
            User ID or None if not found
        """
        row = self.connection.fetchone(
            "SELECT user_id FROM conversations WHERE id = ?",
            (conversation_id,)
        )
        return row['user_id'] if row else None
    
    def list_conversations(self, user_id: str) -> List[dict]:
        """
        List all conversations for a user (summary only).
        
        Args:
            user_id: User ID
            
        Returns:
            List of conversation summaries
        """
        rows = self.connection.fetchall(
            """
            SELECT c.id, c.created_at, c.updated_at,
                   (SELECT COUNT(*) FROM messages WHERE conversation_id = c.id) as message_count,
                   (SELECT content FROM messages WHERE conversation_id = c.id AND role = 'user' ORDER BY timestamp LIMIT 1) as first_message
            FROM conversations c
            WHERE c.user_id = ?
            ORDER BY c.updated_at DESC
            """,
            (user_id,)
        )
        
        return [
            {
                "id": row['id'],
                "created_at": row['created_at'],
                "updated_at": row['updated_at'],
                "message_count": row['message_count'],
                "preview": row['first_message'][:100] if row['first_message'] else None
            }
            for row in rows
        ]
    
    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        citations: Optional[List[Citation]] = None
    ) -> Optional[ConversationMessage]:
        """
        Add a message to a conversation.
        
        Args:
            conversation_id: Conversation ID
            role: Message role ('user' or 'assistant')
            content: Message content
            citations: Optional citations (for assistant messages)
            
        Returns:
            Created message or None if conversation not found
        """
        now = datetime.now()
        
        # Insert message
        cursor = self.connection.execute(
            """
            INSERT INTO messages (conversation_id, role, content, timestamp, metadata)
            VALUES (?, ?, ?, ?, ?)
            """,
            (conversation_id, role, content, now.isoformat(), None)
        )
        
        message_id = cursor.lastrowid
        
        # Insert citations if present
        if citations:
            citation_params = [
                (
                    message_id,
                    c.index,
                    c.article_id,
                    c.article_number,
                    c.article_text,
                    c.normativa_title,
                    c.article_path,
                    c.score
                )
                for c in citations
            ]
            
            self.connection.executemany(
                """
                INSERT INTO message_citations 
                (message_id, citation_index, article_id, article_number, article_text, normativa_title, article_path, score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                citation_params
            )
        
        # Update conversation timestamp
        self.connection.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now.isoformat(), conversation_id)
        )
        
        return ConversationMessage(
            role=role,
            content=content,
            citations=citations or [],
            timestamp=now
        )
    
    def delete_conversation(self, conversation_id: str, user_id: str) -> bool:
        """
        Delete a conversation (with user ownership check).
        
        Args:
            conversation_id: Conversation ID
            user_id: User ID (for ownership verification)
            
        Returns:
            True if deleted
        """
        result = self.connection.execute(
            "DELETE FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id)
        )
        
        deleted = result.rowcount > 0
        if deleted:
            step_logger.info(f"[ConvRepo] Deleted conversation: {conversation_id}")
        
        return deleted
    
    def clear_conversation(self, conversation_id: str, user_id: str) -> bool:
        """
        Clear messages from a conversation (keep conversation).
        
        Args:
            conversation_id: Conversation ID
            user_id: User ID (for ownership verification)
            
        Returns:
            True if cleared
        """
        # Verify ownership
        owner = self.get_conversation_user_id(conversation_id)
        if owner != user_id:
            return False
        
        # Delete messages (cascades to citations)
        self.connection.execute(
            "DELETE FROM messages WHERE conversation_id = ?",
            (conversation_id,)
        )
        
        # Update timestamp
        self.connection.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), conversation_id)
        )
        
        step_logger.info(f"[ConvRepo] Cleared conversation: {conversation_id}")
        return True
    
    def _load_messages(self, conversation: Conversation):
        """Load messages and citations for a conversation."""
        rows = self.connection.fetchall(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY timestamp",
            (conversation.id,)
        )
        
        for row in rows:
            # Load citations for this message
            citations = self._load_citations(row['id'])
            
            message = ConversationMessage(
                role=row['role'],
                content=row['content'],
                citations=citations,
                timestamp=datetime.fromisoformat(row['timestamp']),
                metadata=json.loads(row['metadata']) if row['metadata'] else {}
            )
            
            conversation.messages.append(message)
    
    def _load_citations(self, message_id: int) -> List[Citation]:
        """Load citations for a message."""
        rows = self.connection.fetchall(
            "SELECT * FROM message_citations WHERE message_id = ? ORDER BY citation_index",
            (message_id,)
        )
        
        return [
            Citation(
                index=row['citation_index'],
                article_id=row['article_id'],
                article_number=row['article_number'],
                article_text=row['article_text'] or "",
                normativa_title=row['normativa_title'],
                article_path=row['article_path'] or "",
                score=row['score']
            )
            for row in rows
        ]
