"""
MariaDB Conversation Repository.
Implements conversation and message persistence with SQLAlchemy-compatible queries.
"""
import json
from datetime import datetime
from typing import Optional, List, Dict, Any

from src.infrastructure.database.interface import DatabaseConnection
from src.domain.models.conversation import Conversation, ConversationMessage
from src.domain.models.citation import Citation
from src.utils.logger import step_logger


class MariaDBConversationRepository:
    """
    Repository for conversation persistence in MariaDB.
    
    Uses named parameters (:pN) for SQLAlchemy text() queries.
    """
    
    def __init__(self, connection: DatabaseConnection):
        """Initialize with database connection."""
        self.connection = connection
    
    def create_conversation(self, user_id: str) -> Conversation:
        """Create a new conversation for a user."""
        conversation = Conversation()
        now = datetime.now()
        
        self.connection.execute(
            """
            INSERT INTO conversations (id, user_id, created_at, updated_at, metadata)
            VALUES (:p0, :p1, :p2, :p3, :p4)
            """,
            (
                conversation.id,
                user_id,
                now,
                now,
                json.dumps(conversation.metadata)
            )
        )
        
        step_logger.info(f"[ConvRepo] Created conversation: {conversation.id}")
        return conversation
    
    def get_conversation(
        self, 
        conversation_id: str, 
        user_id: str
    ) -> Optional[Conversation]:
        """Get conversation by ID (with user ownership check)."""
        row = self.connection.fetchone(
            "SELECT * FROM conversations WHERE id = :p0 AND user_id = :p1",
            (conversation_id, user_id)
        )
        
        if row is None:
            return None
        
        conversation = self._row_to_conversation(row)
        self._load_messages(conversation)
        return conversation
    
    def get_conversation_unchecked(self, conversation_id: str) -> Optional[Conversation]:
        """Get conversation by ID without user check."""
        row = self.connection.fetchone(
            "SELECT * FROM conversations WHERE id = :p0",
            (conversation_id,)
        )
        
        if row is None:
            return None
        
        conversation = self._row_to_conversation(row)
        self._load_messages(conversation)
        return conversation
    
    def get_conversation_user_id(self, conversation_id: str) -> Optional[str]:
        """Get the user ID that owns a conversation."""
        row = self.connection.fetchone(
            "SELECT user_id FROM conversations WHERE id = :p0",
            (conversation_id,)
        )
        return row['user_id'] if row else None
    
    def list_conversations(self, user_id: str) -> List[dict]:
        """List all conversations for a user (summary only)."""
        rows = self.connection.fetchall(
            """
            SELECT c.id, c.created_at, c.updated_at,
                   (SELECT COUNT(*) FROM messages WHERE conversation_id = c.id) as message_count,
                   (SELECT content FROM messages WHERE conversation_id = c.id AND role = 'user' ORDER BY timestamp LIMIT 1) as first_message
            FROM conversations c
            WHERE c.user_id = :p0
            ORDER BY c.updated_at DESC
            """,
            (user_id,)
        )
        
        result = []
        for row in rows:
            created_at = row['created_at']
            updated_at = row['updated_at']
            if isinstance(created_at, datetime):
                created_at = created_at.isoformat()
            if isinstance(updated_at, datetime):
                updated_at = updated_at.isoformat()
            
            result.append({
                "id": row['id'],
                "created_at": created_at,
                "updated_at": updated_at,
                "message_count": row['message_count'],
                "preview": row['first_message'][:100] if row['first_message'] else None
            })
        
        return result
    
    def get_metadata(self, conversation_id: str) -> dict:
        """Get metadata for a conversation."""
        row = self.connection.fetchone(
            "SELECT metadata FROM conversations WHERE id = :p0",
            (conversation_id,)
        )
        
        if row and row['metadata']:
            metadata = row['metadata']
            if isinstance(metadata, str):
                return json.loads(metadata)
            return metadata
        return {}
    
    def update_metadata(self, conversation_id: str, metadata: dict) -> bool:
        """Update metadata for a conversation."""
        existing = self.get_metadata(conversation_id)
        existing.update(metadata)
        
        result = self.connection.execute(
            "UPDATE conversations SET metadata = :p0 WHERE id = :p1",
            (json.dumps(existing), conversation_id)
        )
        
        if result.rowcount > 0:
            step_logger.info(f"[ConvRepo] Updated metadata for: {conversation_id}")
            return True
        return False
    
    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        citations: Optional[List[Citation]] = None,
        context_json: Optional[str] = None
    ) -> Optional[ConversationMessage]:
        """Add a message to a conversation."""
        now = datetime.now()
        
        # Insert message with returning ID
        result = self.connection.execute(
            """
            INSERT INTO messages (conversation_id, role, content, timestamp, metadata, context_json)
            VALUES (:p0, :p1, :p2, :p3, :p4, :p5)
            """,
            (conversation_id, role, content, now, None, context_json)
        )
        
        # Get the last inserted ID
        row = self.connection.fetchone("SELECT LAST_INSERT_ID() as id", ())
        message_id = row['id'] if row else None
        
        # Insert citations if present
        if citations and message_id:
            for c in citations:
                self.connection.execute(
                    """
                    INSERT INTO message_citations 
                    (message_id, citation_index, article_id, article_number, article_text, 
                     normativa_title, article_path, score, cite_key, display_text)
                    VALUES (:p0, :p1, :p2, :p3, :p4, :p5, :p6, :p7, :p8, :p9)
                    """,
                    (
                        message_id,
                        c.index,
                        c.article_id,
                        c.article_number,
                        c.article_text,
                        c.normativa_title,
                        c.article_path,
                        c.score,
                        c.cite_key,
                        c.display_text
                    )
                )
        
        # Update conversation timestamp
        self.connection.execute(
            "UPDATE conversations SET updated_at = :p0 WHERE id = :p1",
            (now, conversation_id)
        )
        
        return ConversationMessage(
            role=role,
            content=content,
            citations=citations or [],
            timestamp=now,
            context_json=context_json
        )
    
    def get_last_context(self, conversation_id: str) -> Optional[str]:
        """Get the context_json from the last assistant message."""
        row = self.connection.fetchone(
            """
            SELECT context_json FROM messages 
            WHERE conversation_id = :p0 AND role = 'assistant' AND context_json IS NOT NULL
            ORDER BY timestamp DESC LIMIT 1
            """,
            (conversation_id,)
        )
        return row['context_json'] if row else None
    
    def get_context_history(
        self, 
        conversation_id: str, 
        n: int = 5
    ) -> List[Dict[str, Any]]:
        """Get the last n assistant messages with their context."""
        rows = self.connection.fetchall(
            """
            SELECT id, context_json FROM messages 
            WHERE conversation_id = :p0 AND role = 'assistant' AND context_json IS NOT NULL
            ORDER BY timestamp DESC LIMIT :p1
            """,
            (conversation_id, n)
        )
        
        if not rows:
            return []
        
        result = []
        for i, row in enumerate(rows):
            message_id = row['id']
            context_json = row['context_json']
            citations = self._load_citations(message_id)
            
            result.append({
                "context_json": context_json,
                "citations": citations,
                "is_immediate": (i == 0)
            })
        
        return result
    
    def delete_conversation(self, conversation_id: str, user_id: str) -> bool:
        """Delete a conversation (with user ownership check)."""
        result = self.connection.execute(
            "DELETE FROM conversations WHERE id = :p0 AND user_id = :p1",
            (conversation_id, user_id)
        )
        
        deleted = result.rowcount > 0
        if deleted:
            step_logger.info(f"[ConvRepo] Deleted conversation: {conversation_id}")
        
        return deleted
    
    def clear_conversation(self, conversation_id: str, user_id: str) -> bool:
        """Clear messages from a conversation (keep conversation)."""
        owner = self.get_conversation_user_id(conversation_id)
        if owner != user_id:
            return False
        
        self.connection.execute(
            "DELETE FROM messages WHERE conversation_id = :p0",
            (conversation_id,)
        )
        
        self.connection.execute(
            "UPDATE conversations SET updated_at = :p0 WHERE id = :p1",
            (datetime.now(), conversation_id)
        )
        
        step_logger.info(f"[ConvRepo] Cleared conversation: {conversation_id}")
        return True
    
    def _row_to_conversation(self, row: dict) -> Conversation:
        """Convert row to Conversation object."""
        created_at = row['created_at']
        updated_at = row['updated_at']
        
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        
        metadata = row['metadata']
        if isinstance(metadata, str):
            metadata = json.loads(metadata) if metadata else {}
        elif metadata is None:
            metadata = {}
        
        return Conversation(
            id=row['id'],
            messages=[],
            created_at=created_at,
            updated_at=updated_at,
            metadata=metadata
        )
    
    def _load_messages(self, conversation: Conversation):
        """Load messages for a conversation."""
        rows = self.connection.fetchall(
            "SELECT * FROM messages WHERE conversation_id = :p0 ORDER BY timestamp",
            (conversation.id,)
        )
        
        for row in rows:
            citations = self._load_citations(row['id'])
            
            timestamp = row['timestamp']
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp)
            
            metadata = row.get('metadata')
            if isinstance(metadata, str):
                metadata = json.loads(metadata) if metadata else {}
            elif metadata is None:
                metadata = {}
            
            message = ConversationMessage(
                role=row['role'],
                content=row['content'],
                citations=citations,
                timestamp=timestamp,
                metadata=metadata,
                context_json=row.get('context_json')
            )
            
            conversation.messages.append(message)
    
    def _load_citations(self, message_id: int) -> List[Citation]:
        """Load citations for a message."""
        rows = self.connection.fetchall(
            "SELECT * FROM message_citations WHERE message_id = :p0 ORDER BY citation_index",
            (message_id,)
        )
        
        return [
            Citation(
                cite_key=row['cite_key'],
                article_id=row['article_id'],
                article_number=row['article_number'],
                article_text=row['article_text'] or "",
                normativa_title=row['normativa_title'],
                article_path=row['article_path'] or "",
                display_text=row['display_text'] or "",
                score=row['score'],
                index=row['citation_index']
            )
            for row in rows
        ]
