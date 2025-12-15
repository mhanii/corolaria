"""
Azure OpenAI LLM Provider implementation.
Uses Azure OpenAI Service for chat completions.
Requires azure_endpoint, api_version, and uses deployment names instead of model names.
"""
import os
import time
import functools
import asyncio
from typing import List, Optional, Dict, Any

try:
    from openai import AzureOpenAI, AsyncAzureOpenAI
    from openai import RateLimitError, APIStatusError, APIConnectionError
except ImportError:
    AzureOpenAI = None
    AsyncAzureOpenAI = None
    RateLimitError = None
    APIStatusError = None
    APIConnectionError = None

from src.domain.interfaces.llm_provider import LLMProvider, Message, LLMResponse
from src.utils.logger import step_logger


# Retry configuration
MAX_RETRIES = 5
BASE_DELAY = 2.0  # seconds


def _is_transient_error(e: Exception) -> bool:
    """Check if an exception is a transient error worth retrying."""
    error_str = str(e).lower()
    
    # Check for specific OpenAI error types
    if RateLimitError and isinstance(e, RateLimitError):
        return True
    if APIConnectionError and isinstance(e, APIConnectionError):
        return True
    if APIStatusError and isinstance(e, APIStatusError):
        if hasattr(e, 'status_code') and e.status_code in [429, 500, 502, 503, 504]:
            return True
    
    # Fallback to string matching
    return any(x in error_str for x in [
        '429', 'rate_limit', 'rate limit', 'quota',
        '503', 'unavailable', 'overloaded',
        '500', '502', '504', 'server error',
        'timeout', 'connection'
    ])


def _retry_with_backoff(func):
    """
    Decorator for exponential backoff retry on transient errors.
    
    Handles:
    - 429 Rate Limit errors
    - 503 Service Unavailable
    - Connection errors
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        last_exception = None
        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                
                if not _is_transient_error(e) or attempt == MAX_RETRIES - 1:
                    raise
                
                delay = BASE_DELAY * (2 ** attempt)
                step_logger.warning(
                    f"[AzureOpenAILLMProvider] Transient error, retrying in {delay}s "
                    f"(attempt {attempt + 1}/{MAX_RETRIES}): {e}"
                )
                time.sleep(delay)
        raise last_exception
    return wrapper


class AzureOpenAILLMProvider(LLMProvider):
    """
    LLM provider using Azure OpenAI Service.
    
    Azure OpenAI differs from direct OpenAI:
    - Uses azure_endpoint instead of base_url
    - Requires api_version parameter
    
    Environment variables:
    - AZURE_OPENAI_ENDPOINT: Your Azure resource URL (default: gpt5 cognitive services)
    - AZURE_API_KEY: Your Azure OpenAI API key
    """
    
    def __init__(
        self, 
        model: str = None,
        temperature: float = None,
        max_tokens: int = None,
        api_key: Optional[str] = None,
        azure_endpoint: Optional[str] = None,
        api_version: Optional[str] = None
    ):
        """
        Initialize Azure OpenAI provider.
        
        Args:
            model: Deployment name in Azure (not the OpenAI model name)
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            api_key: Azure OpenAI API key (or set AZURE_OPENAI_API_KEY)
            azure_endpoint: Azure resource URL (or set AZURE_OPENAI_ENDPOINT)
            api_version: API version string (or set AZURE_OPENAI_API_VERSION)
        """
        # Load config for defaults
        from src.config import get_llm_config, get_prompt
        config = get_llm_config()
        
        self.default_system_prompt = get_prompt(
            "llm_default_system_prompt",
            "You are a legal assistant. Cite sources."
        )
        
        # Use config defaults if not provided
        model = model or config.get("model") or "gpt-4o"
        temperature = temperature if temperature is not None else config.get("temperature", 0.3)
        max_tokens = max_tokens if max_tokens is not None else config.get("max_tokens", 8192)
        
        super().__init__(model=model, temperature=temperature, max_tokens=max_tokens)
        
        if AzureOpenAI is None:
            raise ImportError(
                "openai package is not installed. Run: pip install openai"
            )
        
        # Get Azure-specific configuration
        self._api_key = api_key or os.getenv("AZURE_API_KEY")
        self._azure_endpoint = azure_endpoint or os.getenv(
            "AZURE_OPENAI_ENDPOINT", 
            "https://moham-mj4y5l2w-eastus2.cognitiveservices.azure.com/"
        )
        self._api_version = api_version or config.get("azure_api_version") or "2024-12-01-preview"
        
        if not self._api_key:
            raise ValueError("AZURE_API_KEY environment variable is required")
        
        # Create sync client
        self._client = AzureOpenAI(
            api_key=self._api_key,
            api_version=self._api_version,
            azure_endpoint=self._azure_endpoint
        )
        
        # Create async client
        self._async_client = AsyncAzureOpenAI(
            api_key=self._api_key,
            api_version=self._api_version,
            azure_endpoint=self._azure_endpoint
        )
        
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        
        step_logger.info(
            f"[AzureOpenAILLMProvider] Initialized with model={model}, "
            f"endpoint={self._azure_endpoint}, api_version={self._api_version}"
        )
    
    def _build_messages(
        self,
        messages: List[Message],
        context: Optional[str],
        system_prompt: str
    ) -> List[Dict[str, str]]:
        """Build message list with system prompt and optional context."""
        result = []
        
        # Build system message with context
        if context:
            full_system = f"{system_prompt}\n\n---\nCONTEXT:\n{context}\n---"
        else:
            full_system = system_prompt
        
        result.append({"role": "system", "content": full_system})
        
        # Add conversation messages
        for msg in messages:
            result.append({"role": msg.role, "content": msg.content})
        
        return result
    
    @_retry_with_backoff
    def generate(
        self, 
        messages: List[Message], 
        context: Optional[str] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Generate a response using Azure OpenAI.
        
        Includes automatic retry with exponential backoff for transient errors.
        
        Args:
            messages: Conversation history
            context: RAG context to inject
            system_prompt: Custom system prompt (optional)
            **kwargs: Additional generation parameters
            
        Returns:
            LLMResponse with generated content
        """
        system = system_prompt or self.default_system_prompt
        api_messages = self._build_messages(messages, context, system)
        
        step_logger.info(
            f"[AzureOpenAILLMProvider] Generating response "
            f"(messages={len(api_messages)}, deployment={self._model})"
        )
        
        response = self._client.chat.completions.create(
            model=self._model,
            messages=api_messages,
            temperature=self._temperature,
            max_completion_tokens=self._max_tokens,
            **kwargs
        )
        
        # Extract usage info
        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
            step_logger.info(f"[AzureOpenAILLMProvider] Token usage: {usage}")
        
        # Get content and finish reason
        choice = response.choices[0]
        content = choice.message.content or ""
        finish_reason = choice.finish_reason or "stop"
        
        step_logger.info(
            f"[AzureOpenAILLMProvider] Generated response "
            f"(len={len(content)}, finish_reason={finish_reason})"
        )
        
        return LLMResponse(
            content=content,
            model=self.model,
            usage=usage,
            finish_reason=finish_reason,
            metadata={"provider": "azure_openai", "deployment": self._model}
        )
    
    async def agenerate(
        self, 
        messages: List[Message], 
        context: Optional[str] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Async generation using Azure OpenAI.
        
        Includes automatic retry with exponential backoff for transient errors.
        
        Args:
            messages: Conversation history
            context: RAG context to inject
            system_prompt: Custom system prompt (optional)
            **kwargs: Additional generation parameters
            
        Returns:
            LLMResponse with generated content
        """
        system = system_prompt or self.default_system_prompt
        api_messages = self._build_messages(messages, context, system)
        
        step_logger.info(f"[AzureOpenAILLMProvider] Async generating response")
        
        # Retry logic for async
        last_exception = None
        for attempt in range(MAX_RETRIES):
            try:
                response = await self._async_client.chat.completions.create(
                    model=self._model,
                    messages=api_messages,
                    temperature=self._temperature,
                    max_completion_tokens=self._max_tokens,
                    **kwargs
                )
                
                # Extract usage info
                usage = {}
                if response.usage:
                    usage = {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens
                    }
                
                choice = response.choices[0]
                content = choice.message.content or ""
                finish_reason = choice.finish_reason or "stop"
                
                step_logger.info(
                    f"[AzureOpenAILLMProvider] Async generated response "
                    f"(len={len(content)}, finish_reason={finish_reason})"
                )
                
                return LLMResponse(
                    content=content,
                    model=self.model,
                    usage=usage,
                    finish_reason=finish_reason,
                    metadata={"provider": "azure_openai", "deployment": self._model}
                )
                
            except Exception as e:
                last_exception = e
                
                if not _is_transient_error(e) or attempt == MAX_RETRIES - 1:
                    raise
                
                delay = BASE_DELAY * (2 ** attempt)
                step_logger.warning(
                    f"[AzureOpenAILLMProvider] Transient error in async, retrying in {delay}s "
                    f"(attempt {attempt + 1}/{MAX_RETRIES}): {e}"
                )
                await asyncio.sleep(delay)
        
        raise last_exception
    
    def generate_stream(
        self, 
        messages: List[Message], 
        context: Optional[str] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ):
        """
        Stream generation using Azure OpenAI's streaming API.
        
        Includes automatic retry with exponential backoff for transient errors.
        
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
        system = system_prompt or self.default_system_prompt
        api_messages = self._build_messages(messages, context, system)
        
        step_logger.info(f"[AzureOpenAILLMProvider] Starting streaming generation")
        
        # Retry logic wrapping ENTIRE streaming operation
        last_exception = None
        
        for attempt in range(MAX_RETRIES):
            try:
                stream = self._client.chat.completions.create(
                    model=self._model,
                    messages=api_messages,
                    temperature=self._temperature,
                    max_completion_tokens=self._max_tokens,
                    stream=True,
                    stream_options={"include_usage": True},
                    **kwargs
                )
                
                full_content = []
                usage = {}
                finish_reason = "stop"
                
                for chunk in stream:
                    if chunk.choices:
                        choice = chunk.choices[0]
                        
                        # Get content delta
                        if choice.delta and choice.delta.content:
                            text = choice.delta.content
                            full_content.append(text)
                            yield text
                        
                        # Get finish reason
                        if choice.finish_reason:
                            finish_reason = choice.finish_reason
                    
                    # Get usage from final chunk
                    if chunk.usage:
                        usage = {
                            "prompt_tokens": chunk.usage.prompt_tokens,
                            "completion_tokens": chunk.usage.completion_tokens,
                            "total_tokens": chunk.usage.total_tokens
                        }
                
                # Success! Streaming completed
                final_content = "".join(full_content)
                step_logger.info(
                    f"[AzureOpenAILLMProvider] Streaming complete ({len(final_content)} chars)"
                )
                
                return LLMResponse(
                    content=final_content,
                    model=self.model,
                    usage=usage,
                    finish_reason=finish_reason,
                    metadata={"provider": "azure_openai", "streaming": True}
                )
                
            except Exception as e:
                last_exception = e
                
                if not _is_transient_error(e) or attempt == MAX_RETRIES - 1:
                    step_logger.error(f"[AzureOpenAILLMProvider] Streaming failed: {e}")
                    raise
                
                delay = BASE_DELAY * (2 ** attempt)
                step_logger.warning(
                    f"[AzureOpenAILLMProvider] Transient error during streaming, retrying in {delay}s "
                    f"(attempt {attempt + 1}/{MAX_RETRIES}): {e}"
                )
                time.sleep(delay)
        
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
        Async streaming generation using Azure OpenAI.
        
        Includes automatic retry with exponential backoff for transient errors.
        
        Args:
            messages: Conversation history
            context: RAG context to inject
            system_prompt: Custom system prompt (optional)
            **kwargs: Additional generation parameters
            
        Yields:
            str or dict: Text chunks, then final {"_final_response": LLMResponse}
        """
        system = system_prompt or self.default_system_prompt
        api_messages = self._build_messages(messages, context, system)
        
        step_logger.info(f"[AzureOpenAILLMProvider] Starting async streaming generation")
        
        # Retry logic wrapping ENTIRE streaming operation
        last_exception = None
        
        for attempt in range(MAX_RETRIES):
            try:
                stream = await self._async_client.chat.completions.create(
                    model=self._model,
                    messages=api_messages,
                    temperature=self._temperature,
                    max_completion_tokens=self._max_tokens,
                    stream=True,
                    stream_options={"include_usage": True},
                    **kwargs
                )
                
                full_content = []
                usage = {}
                finish_reason = "stop"
                
                async for chunk in stream:
                    if chunk.choices:
                        choice = chunk.choices[0]
                        
                        # Get content delta
                        if choice.delta and choice.delta.content:
                            text = choice.delta.content
                            full_content.append(text)
                            yield text
                        
                        # Get finish reason
                        if choice.finish_reason:
                            finish_reason = choice.finish_reason
                    
                    # Get usage from final chunk
                    if chunk.usage:
                        usage = {
                            "prompt_tokens": chunk.usage.prompt_tokens,
                            "completion_tokens": chunk.usage.completion_tokens,
                            "total_tokens": chunk.usage.total_tokens
                        }
                
                # Success! Streaming completed
                final_content = "".join(full_content)
                step_logger.info(
                    f"[AzureOpenAILLMProvider] Async streaming complete ({len(final_content)} chars)"
                )
                
                final_response = LLMResponse(
                    content=final_content,
                    model=self.model,
                    usage=usage,
                    finish_reason=finish_reason,
                    metadata={"provider": "azure_openai", "streaming": True}
                )
                
                # Yield final response marker
                yield {"_final_response": final_response}
                return  # Exit retry loop on success
                
            except Exception as e:
                last_exception = e
                
                if not _is_transient_error(e) or attempt == MAX_RETRIES - 1:
                    step_logger.error(f"[AzureOpenAILLMProvider] Async streaming failed: {e}")
                    raise
                
                delay = BASE_DELAY * (2 ** attempt)
                step_logger.warning(
                    f"[AzureOpenAILLMProvider] Transient error during async streaming, retrying in {delay}s "
                    f"(attempt {attempt + 1}/{MAX_RETRIES}): {e}"
                )
                await asyncio.sleep(delay)
        
        if last_exception:
            raise last_exception
