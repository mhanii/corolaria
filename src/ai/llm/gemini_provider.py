"""
Gemini LLM Provider implementation.
Uses Google's GenAI SDK (google.genai) for chat completions.
This SDK is properly instrumented by openinference-instrumentation-google-genai.
"""
import os
import time
import functools
from typing import List, Optional, Dict, Any

try:
    from google import genai
    from google.genai import types
    from google.genai.errors import ClientError, ServerError
except ImportError:
    genai = None
    types = None
    ClientError = None
    ServerError = None

from src.domain.interfaces.llm_provider import LLMProvider, Message, LLMResponse
from src.utils.logger import step_logger


# Retry configuration
MAX_RETRIES = 5
BASE_DELAY = 2.0  # seconds


def _retry_with_backoff(func):
    """
    Decorator for exponential backoff retry on transient errors.
    
    Handles:
    - 429 RESOURCE_EXHAUSTED: Rate limit exceeded, wait and retry
    - 503 UNAVAILABLE: Model overloaded, retry with backoff
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        last_exception = None
        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                error_str = str(e).lower()
                
                # Check for transient errors worth retrying
                is_transient = any(x in error_str for x in [
                    '429', 'resource_exhausted', 'rate limit', 'quota',
                    '503', 'unavailable', 'overloaded',
                    '500', '502', '504', 'server error',
                    'timeout', 'connection'
                ])
                
                if not is_transient or attempt == MAX_RETRIES - 1:
                    raise
                
                delay = BASE_DELAY * (2 ** attempt)
                step_logger.warning(
                    f"[GeminiLLMProvider] Transient error, retrying in {delay}s "
                    f"(attempt {attempt + 1}/{MAX_RETRIES}): {e}"
                )
                time.sleep(delay)
        raise last_exception
    return wrapper


async def _async_retry_with_backoff(coro_func):
    """
    Async version of retry decorator for transient errors.
    Returns an async wrapper function.
    """
    @functools.wraps(coro_func)
    async def wrapper(*args, **kwargs):
        import asyncio
        last_exception = None
        for attempt in range(MAX_RETRIES):
            try:
                return await coro_func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                error_str = str(e).lower()
                
                is_transient = any(x in error_str for x in [
                    '429', 'resource_exhausted', 'rate limit', 'quota',
                    '503', 'unavailable', 'overloaded',
                    '500', '502', '504', 'server error',
                    'timeout', 'connection'
                ])
                
                if not is_transient or attempt == MAX_RETRIES - 1:
                    raise
                
                delay = BASE_DELAY * (2 ** attempt)
                step_logger.warning(
                    f"[GeminiLLMProvider] Transient error, retrying in {delay}s "
                    f"(attempt {attempt + 1}/{MAX_RETRIES}): {e}"
                )
                await asyncio.sleep(delay)
        raise last_exception
    return wrapper


class GeminiLLMProvider(LLMProvider):
    """
    LLM provider using Google Gemini models via google.genai SDK.
    Default model: gemini-2.5-flash (fast, cost-effective)
    Alternative: gemini-1.5-pro (more capable)
    
    Uses the new google.genai SDK which is properly instrumented by
    openinference-instrumentation-google-genai for Phoenix token tracking.
    """
    
    DEFAULT_SYSTEM_PROMPT = """You are a legal assistant answering questions based solely on provided context.
Always cite sources using [cite:ID]article text[/cite] format where ID matches the source identifier.
Be concise and accurate. If context lacks relevant info, say so clearly."""
    
    def __init__(
        self, 
        model: str = "gemini-2.5-flash",
        temperature: float = 0.3,
        max_tokens: int = 8192,
        api_key: Optional[str] = None
    ):
        super().__init__(model=model, temperature=temperature, max_tokens=max_tokens)
        
        if genai is None:
            raise ImportError("google-genai is not installed. Run: pip install google-genai")
        
        # Configure API key
        api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is required")
        
        # Create client using new SDK
        self._client = genai.Client(api_key=api_key)
        self._model_name = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        
        # Safety settings - disable all filters for legal content
        # Legal text can trigger false positives on topics like criminal law, etc.
        self._safety_settings = [
            types.SafetySetting(
                category="HARM_CATEGORY_HARASSMENT",
                threshold="BLOCK_NONE"
            ),
            types.SafetySetting(
                category="HARM_CATEGORY_HATE_SPEECH", 
                threshold="BLOCK_NONE"
            ),
            types.SafetySetting(
                category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                threshold="BLOCK_NONE"
            ),
            types.SafetySetting(
                category="HARM_CATEGORY_DANGEROUS_CONTENT",
                threshold="BLOCK_NONE"
            ),
        ]
        
        step_logger.info(f"[GeminiLLMProvider] Initialized with model={model} (using google.genai SDK)")
    
    @_retry_with_backoff
    def generate(
        self, 
        messages: List[Message], 
        context: Optional[str] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Generate a response using Gemini.
        
        Includes automatic retry with exponential backoff for transient errors
        like 429 RESOURCE_EXHAUSTED and 503 UNAVAILABLE.
        
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
        
        # Use the new SDK's generate_content method via client.models
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                temperature=self._temperature,
                safety_settings=self._safety_settings
            )
        )
        
        # Extract usage info - this is what Phoenix will track
        usage = {}
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            usage = {
                "prompt_tokens": getattr(response.usage_metadata, 'prompt_token_count', 0),
                "completion_tokens": getattr(response.usage_metadata, 'candidates_token_count', 0),
                "total_tokens": getattr(response.usage_metadata, 'total_token_count', 0)
            }
            step_logger.info(f"[GeminiLLMProvider] Token usage: {usage}")
        
        # Handle response
        finish_reason = "stop"
        content = ""
        
        if response.candidates:
            candidate = response.candidates[0]
            finish_reason_raw = getattr(candidate, 'finish_reason', None)
            
            # Handle finish reason
            if finish_reason_raw:
                if hasattr(finish_reason_raw, 'name'):
                    finish_reason = finish_reason_raw.name.lower()
                else:
                    finish_reason = str(finish_reason_raw).lower()
            
            step_logger.info(f"[GeminiLLMProvider] finish_reason: {finish_reason}")
            
            # Check if response was blocked by safety filters
            if finish_reason == "safety":
                step_logger.warning("[GeminiLLMProvider] Response blocked by safety filters")
                content = ("Lo siento, no puedo responder a esa pregunta porque el contenido "
                           "ha sido bloqueado por los filtros de seguridad. Por favor, reformula "
                           "tu consulta de manera diferente.")
            elif candidate.content and candidate.content.parts:
                content = candidate.content.parts[0].text
            else:
                step_logger.warning(f"[GeminiLLMProvider] Empty content, finish_reason={finish_reason}")
                content = ""
        else:
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
    
    def generate_stream(
        self, 
        messages: List[Message], 
        context: Optional[str] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ):
        """
        Stream generation using Gemini's streaming API.
        
        Includes automatic retry with exponential backoff for transient errors
        like 429 RESOURCE_EXHAUSTED and 503 UNAVAILABLE. If an error occurs
        during streaming, the entire operation is retried from the beginning.
        
        Args:
            messages: Conversation history
            context: RAG context to inject
            system_prompt: Custom system prompt (optional)
            **kwargs: Additional generation parameters
            
        Yields:
            str: Text chunks as they are generated
            
        Returns:
            LLMResponse with final content and usage (via generator return)
        """
        system = system_prompt or self.DEFAULT_SYSTEM_PROMPT
        
        # Build prompt with context
        prompt_parts = []
        
        if context:
            prompt_parts.append(f"{system}\n\n---\nCONTEXT:\n{context}\n---\n")
        else:
            prompt_parts.append(f"{system}\n\n")
        
        for msg in messages:
            if msg.role == "user":
                prompt_parts.append(f"User: {msg.content}\n")
            elif msg.role == "assistant":
                prompt_parts.append(f"Assistant: {msg.content}\n")
        
        full_prompt = "".join(prompt_parts)
        
        step_logger.info(f"[GeminiLLMProvider] Starting streaming generation (prompt_len={len(full_prompt)})")
        
        # Retry logic wrapping ENTIRE streaming operation (init + iteration)
        last_exception = None
        
        for attempt in range(MAX_RETRIES):
            try:
                # Use streaming API
                response_stream = self._client.models.generate_content_stream(
                    model=self._model_name,
                    contents=full_prompt,
                    config=types.GenerateContentConfig(
                        temperature=self._temperature,
                        safety_settings=self._safety_settings
                    )
                )
                
                full_content = []
                usage = {}
                finish_reason = "stop"
                
                # Iterate through stream - errors here will also trigger retry
                for chunk in response_stream:
                    if chunk.candidates:
                        candidate = chunk.candidates[0]
                        if candidate.content and candidate.content.parts:
                            text = candidate.content.parts[0].text
                            if text:
                                full_content.append(text)
                                yield text
                        
                        # Check finish reason
                        if hasattr(candidate, 'finish_reason') and candidate.finish_reason:
                            fr = candidate.finish_reason
                            if hasattr(fr, 'name'):
                                finish_reason = fr.name.lower()
                            else:
                                finish_reason = str(fr).lower()
                    
                    # Get usage metadata from final chunk
                    if hasattr(chunk, 'usage_metadata') and chunk.usage_metadata:
                        usage = {
                            "prompt_tokens": getattr(chunk.usage_metadata, 'prompt_token_count', 0),
                            "completion_tokens": getattr(chunk.usage_metadata, 'candidates_token_count', 0),
                            "total_tokens": getattr(chunk.usage_metadata, 'total_token_count', 0)
                        }
                
                # Success! Streaming completed without error
                final_content = "".join(full_content)
                step_logger.info(f"[GeminiLLMProvider] Streaming complete ({len(final_content)} chars)")
                
                return LLMResponse(
                    content=final_content,
                    model=self.model,
                    usage=usage,
                    finish_reason=finish_reason,
                    metadata={"provider": "gemini", "streaming": True}
                )
                
            except Exception as e:
                last_exception = e
                error_str = str(e).lower()
                
                is_transient = any(x in error_str for x in [
                    '429', 'resource_exhausted', 'rate limit', 'quota',
                    '503', 'unavailable', 'overloaded',
                    '500', '502', '504', 'server error',
                    'timeout', 'connection'
                ])
                
                if not is_transient or attempt == MAX_RETRIES - 1:
                    step_logger.error(f"[GeminiLLMProvider] Streaming generation failed: {e}")
                    raise
                
                delay = BASE_DELAY * (2 ** attempt)
                step_logger.warning(
                    f"[GeminiLLMProvider] Transient error during streaming, retrying in {delay}s "
                    f"(attempt {attempt + 1}/{MAX_RETRIES}): {e}"
                )
                time.sleep(delay)
        
        # All retries exhausted
        if last_exception:
            raise last_exception
    
    async def agenerate_stream(
        self, 
        messages: List[Message], 
        context: Optional[str] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ):
        """
        Async streaming generation using Gemini.
        
        Includes automatic retry with exponential backoff for transient errors
        like 429 RESOURCE_EXHAUSTED and 503 UNAVAILABLE. If an error occurs
        during streaming, the entire operation is retried from the beginning.
        
        Note: Gemini SDK async streaming support is limited.
        This wraps the sync streaming for async contexts.
        
        Args:
            messages: Conversation history
            context: RAG context to inject
            system_prompt: Custom system prompt (optional)
            **kwargs: Additional generation parameters
            
        Yields:
            str or dict: Text chunks, then final {"_final_response": LLMResponse}
        """
        import asyncio
        
        system = system_prompt or self.DEFAULT_SYSTEM_PROMPT
        
        # Build prompt with context
        prompt_parts = []
        
        if context:
            prompt_parts.append(f"{system}\n\n---\nCONTEXT:\n{context}\n---\n")
        else:
            prompt_parts.append(f"{system}\n\n")
        
        for msg in messages:
            if msg.role == "user":
                prompt_parts.append(f"User: {msg.content}\n")
            elif msg.role == "assistant":
                prompt_parts.append(f"Assistant: {msg.content}\n")
        
        full_prompt = "".join(prompt_parts)
        
        step_logger.info(f"[GeminiLLMProvider] Starting async streaming generation")
        
        # Retry logic wrapping ENTIRE streaming operation (init + iteration)
        last_exception = None
        
        for attempt in range(MAX_RETRIES):
            try:
                # Use streaming API
                response_stream = self._client.models.generate_content_stream(
                    model=self._model_name,
                    contents=full_prompt,
                    config=types.GenerateContentConfig(
                        temperature=self._temperature,
                        safety_settings=self._safety_settings
                    )
                )
                
                full_content = []
                usage = {}
                finish_reason = "stop"
                
                # Iterate through stream - errors here will also trigger retry
                for chunk in response_stream:
                    if chunk.candidates:
                        candidate = chunk.candidates[0]
                        if candidate.content and candidate.content.parts:
                            text = candidate.content.parts[0].text
                            if text:
                                full_content.append(text)
                                yield text
                        
                        if hasattr(candidate, 'finish_reason') and candidate.finish_reason:
                            fr = candidate.finish_reason
                            if hasattr(fr, 'name'):
                                finish_reason = fr.name.lower()
                            else:
                                finish_reason = str(fr).lower()
                    
                    if hasattr(chunk, 'usage_metadata') and chunk.usage_metadata:
                        usage = {
                            "prompt_tokens": getattr(chunk.usage_metadata, 'prompt_token_count', 0),
                            "completion_tokens": getattr(chunk.usage_metadata, 'candidates_token_count', 0),
                            "total_tokens": getattr(chunk.usage_metadata, 'total_token_count', 0)
                        }
                    
                    # Yield control to event loop periodically
                    await asyncio.sleep(0)
                
                # Success! Streaming completed without error
                final_content = "".join(full_content)
                step_logger.info(f"[GeminiLLMProvider] Async streaming complete ({len(final_content)} chars)")
                
                final_response = LLMResponse(
                    content=final_content,
                    model=self.model,
                    usage=usage,
                    finish_reason=finish_reason,
                    metadata={"provider": "gemini", "streaming": True}
                )
                
                # Yield final response marker
                yield {"_final_response": final_response}
                return  # Exit the retry loop on success
                
            except Exception as e:
                last_exception = e
                error_str = str(e).lower()
                
                is_transient = any(x in error_str for x in [
                    '429', 'resource_exhausted', 'rate limit', 'quota',
                    '503', 'unavailable', 'overloaded',
                    '500', '502', '504', 'server error',
                    'timeout', 'connection'
                ])
                
                if not is_transient or attempt == MAX_RETRIES - 1:
                    step_logger.error(f"[GeminiLLMProvider] Async streaming failed: {e}")
                    raise
                
                delay = BASE_DELAY * (2 ** attempt)
                step_logger.warning(
                    f"[GeminiLLMProvider] Transient error during streaming, retrying in {delay}s "
                    f"(attempt {attempt + 1}/{MAX_RETRIES}): {e}"
                )
                await asyncio.sleep(delay)
        
        # All retries exhausted
        if last_exception:
            raise last_exception
