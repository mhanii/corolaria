"""
Gemini LLM Provider implementation.
Uses Google's Generative AI SDK for chat completions.
"""
import os
from typing import List, Optional, Dict, Any
import google.generativeai as genai

from src.domain.interfaces.llm_provider import LLMProvider, Message, LLMResponse
from src.utils.logger import step_logger


class GeminiLLMProvider(LLMProvider):
    """
    LLM provider using Google Gemini models.
    Default model: gemini-2.5-flash (fast, cost-effective)
    Alternative: gemini-1.5-pro (more capable)
    """
    
    DEFAULT_SYSTEM_PROMPT = """You are a legal assistant answering questions based solely on provided context.
Always cite sources using [1], [2] format referencing source numbers.
Be concise and accurate. If context lacks relevant info, say so clearly."""
    
    def __init__(
        self, 
        model: str = "gemini-2.5-flash",
        temperature: float = 0.3,
        max_tokens: int = 1024,
        api_key: Optional[str] = None
    ):
        super().__init__(model=model, temperature=temperature, max_tokens=max_tokens)
        
        # Configure API key
        api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is required")
        
        genai.configure(api_key=api_key)
        
        # Initialize model
        self._model = genai.GenerativeModel(
            model_name=model,
            generation_config=genai.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            )
        )
        
        step_logger.info(f"[GeminiLLMProvider] Initialized with model={model}")
    
    def generate(
        self, 
        messages: List[Message], 
        context: Optional[str] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Generate a response using Gemini.
        
        Args:
            messages: Conversation history
            context: RAG context to inject
            system_prompt: Custom system prompt (optional)
            **kwargs: Additional generation parameters
            
        Returns:
            LLMResponse with generated content
        """
        system = system_prompt or self.DEFAULT_SYSTEM_PROMPT
        
        # Build prompt with context
        prompt_parts = []
        
        # Add system instruction with context
        if context:
            prompt_parts.append(f"{system}\n\n---\nCONTEXT:\n{context}\n---\n")
        else:
            prompt_parts.append(f"{system}\n\n")
        
        # Add conversation history
        for msg in messages:
            if msg.role == "user":
                prompt_parts.append(f"User: {msg.content}\n")
            elif msg.role == "assistant":
                prompt_parts.append(f"Assistant: {msg.content}\n")
        
        # Final prompt
        full_prompt = "".join(prompt_parts)
        
        step_logger.info(f"[GeminiLLMProvider] Generating response (prompt_len={len(full_prompt)})")
        
        try:
            response = self._model.generate_content(full_prompt)
            
            # Extract usage info if available
            usage = {}
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                usage = {
                    "prompt_tokens": getattr(response.usage_metadata, 'prompt_token_count', 0),
                    "completion_tokens": getattr(response.usage_metadata, 'candidates_token_count', 0),
                    "total_tokens": getattr(response.usage_metadata, 'total_token_count', 0)
                }
            
            # Handle blocked responses (safety filters, etc.)
            # finish_reason values: 1=STOP, 2=SAFETY, 3=RECITATION, 4=OTHER, 5=MAX_TOKENS
            finish_reason = "stop"
            content = ""
            
            if response.candidates:
                candidate = response.candidates[0]
                finish_reason_value = getattr(candidate, 'finish_reason', None)
                
                # Map numeric finish_reason to string
                finish_reason_map = {
                    1: "stop",
                    2: "safety",
                    3: "recitation",
                    4: "other",
                    5: "max_tokens"
                }
                finish_reason = finish_reason_map.get(finish_reason_value, str(finish_reason_value))
                
                # Check if response was blocked by safety filters
                if finish_reason_value == 2:  # SAFETY
                    step_logger.warning("[GeminiLLMProvider] Response blocked by safety filters")
                    content = ("Lo siento, no puedo responder a esa pregunta porque el contenido "
                               "ha sido bloqueado por los filtros de seguridad. Por favor, reformula "
                               "tu consulta de manera diferente.")
                elif candidate.content and candidate.content.parts:
                    content = candidate.content.parts[0].text
                else:
                    content = ""
            else:
                # No candidates at all - unusual but handle gracefully
                step_logger.warning("[GeminiLLMProvider] No candidates in response")
                content = "No se pudo generar una respuesta. Por favor, intenta de nuevo."
            
            step_logger.info(f"[GeminiLLMProvider] Generated response (len={len(content)}, finish_reason={finish_reason})")
            
            return LLMResponse(
                content=content,
                model=self.model,
                usage=usage,
                finish_reason=finish_reason,
                metadata={"provider": "gemini"}
            )
            
        except Exception as e:
            step_logger.error(f"[GeminiLLMProvider] Generation failed: {e}")
            raise
    
    async def agenerate(
        self, 
        messages: List[Message], 
        context: Optional[str] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Async generation using Gemini.
        Note: Currently wraps sync call; Gemini SDK async support is limited.
        
        Args:
            messages: Conversation history
            context: RAG context to inject
            system_prompt: Custom system prompt (optional)
            **kwargs: Additional generation parameters
            
        Returns:
            LLMResponse with generated content
        """
        # Gemini SDK doesn't have full async support yet
        # Using sync version for now
        return self.generate(messages, context, system_prompt, **kwargs)
