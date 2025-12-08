"""
Abstract interface for LLM providers.
Defines contract for language model integrations (Gemini, OpenAI, Anthropic, etc.)
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Message:
    """Represents a message in a conversation."""
    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, str]:
        """Convert to dict format expected by LLM APIs."""
        return {"role": self.role, "content": self.content}


@dataclass
class LLMResponse:
    """Response from an LLM provider."""
    content: str
    model: str
    usage: Dict[str, int] = field(default_factory=dict)  # tokens used
    finish_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.
    Supports both synchronous and streaming generation.
    """
    
    def __init__(self, model: str, temperature: float = 0.3, max_tokens: int = 8192):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
    
    @abstractmethod
    def generate(
        self, 
        messages: List[Message], 
        context: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Generate a response from the LLM.
        
        Args:
            messages: Conversation history
            context: Optional RAG context to inject
            **kwargs: Provider-specific parameters
            
        Returns:
            LLMResponse with generated content
        """
        pass
    
    @abstractmethod
    async def agenerate(
        self, 
        messages: List[Message], 
        context: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Async version of generate.
        
        Args:
            messages: Conversation history
            context: Optional RAG context to inject
            **kwargs: Provider-specific parameters
            
        Returns:
            LLMResponse with generated content
        """
        pass
    
    def _build_messages_with_context(
        self, 
        messages: List[Message], 
        context: Optional[str],
        system_prompt: str
    ) -> List[Dict[str, str]]:
        """
        Build message list with system prompt and optional context.
        
        Args:
            messages: User/assistant messages
            context: RAG context to inject
            system_prompt: Base system instructions
            
        Returns:
            List of message dicts ready for LLM API
        """
        result = []
        
        # Build system message with context
        if context:
            full_system = f"{system_prompt}\n\n---\nCONTEXT:\n{context}\n---"
        else:
            full_system = system_prompt
        
        result.append({"role": "system", "content": full_system})
        
        # Add conversation messages
        for msg in messages:
            result.append(msg.to_dict())
        
        return result
