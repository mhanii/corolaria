"""
Resilient LLM Provider.

Wraps multiple LLM providers with automatic fallback and retry logic.
Tries Main → Backup → Fallback with configurable retry strategies.
Now includes analytics integration for error and provider tracking.

Configuration loaded from config/config.yaml under llm.resilient section.
"""
import time
import asyncio
from typing import List, Optional, Dict, Any, Generator, AsyncGenerator

from src.domain.interfaces.llm_provider import LLMProvider, Message, LLMResponse
from src.ai.llm.factory import LLMFactory
from src.config import get_llm_config
from src.utils.logger import step_logger


def _get_analytics():
    """Lazy load analytics service to avoid circular imports."""
    try:
        from src.domain.services.analytics_service import get_analytics_service
        return get_analytics_service()
    except Exception:
        return None


def _record_error(e: Exception, provider_name: str):
    """Record an error to analytics if available."""
    analytics = _get_analytics()
    if not analytics:
        return
    
    error_str = str(e).lower()
    if '429' in error_str or 'rate_limit' in error_str or 'resource_exhausted' in error_str:
        analytics.record_rate_limit_error(provider=provider_name, error_message=str(e))
    elif '503' in error_str or 'unavailable' in error_str:
        analytics.record_service_unavailable(provider=provider_name, error_message=str(e))
    elif '500' in error_str or 'server error' in error_str:
        analytics.record_server_error(error_message=str(e))


def _record_provider_used(provider_name: str):
    """Record which provider was successfully used."""
    analytics = _get_analytics()
    if analytics:
        analytics.record_provider_used(provider=provider_name)


def _is_retriable_error(e: Exception) -> bool:
    """Check if an exception is a retriable error (429, 503, etc.)."""
    error_str = str(e).lower()
    return any(x in error_str for x in [
        '429', 'rate_limit', 'rate limit', 'quota', 'resource_exhausted',
        '503', 'unavailable', 'overloaded',
        '500', '502', '504', 'server error',
        'timeout', 'connection'
    ])


class ResilientLLMProvider(LLMProvider):
    """
    Resilient LLM provider with automatic fallback between multiple providers.
    
    Fallback strategy:
    1. Main provider with N retries and exponential backoff
    2. Backup provider with M retries and exponential backoff  
    3. Fallback provider (single attempt, most reliable)
    
    Configuration from config/config.yaml:
    ```yaml
    llm:
      resilient:
        enabled: true
        main:
          provider: "gemini"
          model: "gemini-2.0-flash"
          retries: 3
          delays: [2, 4, 8]
        backup:
          provider: "azure_openai"
          model: "gpt-5-mini"
          retries: 2
          delays: [2, 4]
        fallback:
          provider: "gemini"
          model: "gemini-2.5-flash"
    ```
    """
    
    def __init__(self):
        """Initialize all three providers from config."""
        config = get_llm_config()
        resilient_config = config.get("resilient", {})
        
        if not resilient_config.get("enabled", False):
            raise ValueError(
                "ResilientLLMProvider requires llm.resilient.enabled=true in config"
            )
        
        # Initialize all three providers
        step_logger.info("[ResilientLLMProvider] Initializing providers...")
        
        main_config = resilient_config.get("main", {})
        backup_config = resilient_config.get("backup", {})
        fallback_config = resilient_config.get("fallback", {})
        
        # Create providers
        self._main_provider = self._create_provider("main", main_config)
        self._backup_provider = self._create_provider("backup", backup_config)
        self._fallback_provider = self._create_provider("fallback", fallback_config)
        
        # Store retry configs
        self._main_retries = main_config.get("retries", 3)
        self._main_delays = main_config.get("delays", [2, 4, 8])
        self._backup_retries = backup_config.get("retries", 2)
        self._backup_delays = backup_config.get("delays", [2, 4])
        
        # Use main provider's settings as base
        super().__init__(
            model=main_config.get("model", "gemini-2.0-flash"),
            temperature=main_config.get("temperature", 1),
            max_tokens=config.get("max_tokens", 8192)
        )
        
        step_logger.info(
            f"[ResilientLLMProvider] Ready with 3 providers:\n"
            f"  Main: {main_config.get('provider')}/{main_config.get('model')} "
            f"({self._main_retries} retries)\n"
            f"  Backup: {backup_config.get('provider')}/{backup_config.get('model')} "
            f"({self._backup_retries} retries)\n"
            f"  Fallback: {fallback_config.get('provider')}/{fallback_config.get('model')}"
        )
    
    def _create_provider(self, name: str, config: Dict) -> LLMProvider:
        """Create a single provider from config."""
        provider = config.get("provider", "gemini")
        model = config.get("model", "gemini-2.0-flash")
        temperature = config.get("temperature", 1)
        
        step_logger.info(
            f"[ResilientLLMProvider] Creating {name} provider: {provider}/{model}"
        )
        
        return LLMFactory.create(
            provider=provider,
            model=model,
            temperature=temperature
        )
    
    def _try_with_retries(
        self, 
        provider: LLMProvider, 
        provider_name: str,
        max_retries: int,
        delays: List[int],
        func_name: str,
        *args, 
        **kwargs
    ) -> Optional[LLMResponse]:
        """
        Try calling a provider method with retries.
        
        Returns LLMResponse on success, None if all retries exhausted.
        """
        func = getattr(provider, func_name)
        
        for attempt in range(max_retries):
            try:
                step_logger.info(
                    f"[ResilientLLMProvider] Trying {provider_name} "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                return func(*args, **kwargs)
                
            except Exception as e:
                # Record error to analytics
                _record_error(e, provider_name)
                
                if not _is_retriable_error(e):
                    step_logger.error(
                        f"[ResilientLLMProvider] {provider_name} non-retriable error: {e}"
                    )
                    return None
                
                if attempt < max_retries - 1:
                    delay = delays[min(attempt, len(delays) - 1)]
                    step_logger.warning(
                        f"[ResilientLLMProvider] {provider_name} retriable error, "
                        f"waiting {delay}s: {e}"
                    )
                    time.sleep(delay)
                else:
                    step_logger.warning(
                        f"[ResilientLLMProvider] {provider_name} exhausted retries: {e}"
                    )
        
        return None
    
    async def _try_with_retries_async(
        self, 
        provider: LLMProvider, 
        provider_name: str,
        max_retries: int,
        delays: List[int],
        func_name: str,
        *args, 
        **kwargs
    ) -> Optional[LLMResponse]:
        """Async version of retry logic."""
        func = getattr(provider, func_name)
        
        for attempt in range(max_retries):
            try:
                step_logger.info(
                    f"[ResilientLLMProvider] Trying {provider_name} async "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                return await func(*args, **kwargs)
                
            except Exception as e:
                # Record error to analytics
                _record_error(e, provider_name)
                
                if not _is_retriable_error(e):
                    step_logger.error(
                        f"[ResilientLLMProvider] {provider_name} non-retriable error: {e}"
                    )
                    return None
                
                if attempt < max_retries - 1:
                    delay = delays[min(attempt, len(delays) - 1)]
                    step_logger.warning(
                        f"[ResilientLLMProvider] {provider_name} retriable error, "
                        f"waiting {delay}s: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    step_logger.warning(
                        f"[ResilientLLMProvider] {provider_name} exhausted retries: {e}"
                    )
        
        return None
    
    def generate(
        self, 
        messages: List[Message], 
        context: Optional[str] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Generate response with automatic fallback.
        
        Tries: Main → Backup → Fallback
        """
        # Try main provider
        result = self._try_with_retries(
            self._main_provider, "Main",
            self._main_retries, self._main_delays,
            "generate", messages, context, system_prompt, **kwargs
        )
        if result:
            result.metadata["provider_used"] = "main"
            _record_provider_used("main")
            return result
        
        # Try backup provider
        step_logger.info("[ResilientLLMProvider] Main failed, trying Backup...")
        result = self._try_with_retries(
            self._backup_provider, "Backup",
            self._backup_retries, self._backup_delays,
            "generate", messages, context, system_prompt, **kwargs
        )
        if result:
            result.metadata["provider_used"] = "backup"
            _record_provider_used("backup")
            return result
        
        # Use fallback (no retries, should be most reliable)
        step_logger.info("[ResilientLLMProvider] Backup failed, using Fallback...")
        try:
            result = self._fallback_provider.generate(
                messages, context, system_prompt, **kwargs
            )
            result.metadata["provider_used"] = "fallback"
            _record_provider_used("fallback")
            return result
        except Exception as e:
            _record_error(e, "Fallback")
            step_logger.error(f"[ResilientLLMProvider] All providers failed: {e}")
            raise
    
    async def agenerate(
        self, 
        messages: List[Message], 
        context: Optional[str] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """Async generate with automatic fallback."""
        # Try main provider
        result = await self._try_with_retries_async(
            self._main_provider, "Main",
            self._main_retries, self._main_delays,
            "agenerate", messages, context, system_prompt, **kwargs
        )
        if result:
            result.metadata["provider_used"] = "main"
            _record_provider_used("main")
            return result
        
        # Try backup provider
        step_logger.info("[ResilientLLMProvider] Main failed, trying Backup...")
        result = await self._try_with_retries_async(
            self._backup_provider, "Backup",
            self._backup_retries, self._backup_delays,
            "agenerate", messages, context, system_prompt, **kwargs
        )
        if result:
            result.metadata["provider_used"] = "backup"
            _record_provider_used("backup")
            return result
        
        # Use fallback
        step_logger.info("[ResilientLLMProvider] Backup failed, using Fallback...")
        try:
            result = await self._fallback_provider.agenerate(
                messages, context, system_prompt, **kwargs
            )
            result.metadata["provider_used"] = "fallback"
            _record_provider_used("fallback")
            return result
        except Exception as e:
            _record_error(e, "Fallback")
            step_logger.error(f"[ResilientLLMProvider] All providers failed: {e}")
            raise
    
    def generate_stream(
        self, 
        messages: List[Message], 
        context: Optional[str] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> Generator[str, None, LLMResponse]:
        """Stream generate with fallback - tries each provider until one works."""
        providers = [
            (self._main_provider, "Main", self._main_retries, self._main_delays),
            (self._backup_provider, "Backup", self._backup_retries, self._backup_delays),
            (self._fallback_provider, "Fallback", 1, [0]),
        ]
        
        last_error = None
        
        for provider, name, max_retries, delays in providers:
            for attempt in range(max_retries):
                try:
                    step_logger.info(
                        f"[ResilientLLMProvider] Streaming with {name} "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    
                    gen = provider.generate_stream(
                        messages, context, system_prompt, **kwargs
                    )
                    
                    # Yield all chunks
                    try:
                        while True:
                            chunk = next(gen)
                            yield chunk
                    except StopIteration as e:
                        result = e.value
                        if result:
                            result.metadata["provider_used"] = name.lower()
                        return result
                    
                except Exception as e:
                    last_error = e
                    if not _is_retriable_error(e):
                        step_logger.error(f"[ResilientLLMProvider] {name} non-retriable: {e}")
                        break
                    
                    if attempt < max_retries - 1:
                        delay = delays[min(attempt, len(delays) - 1)]
                        step_logger.warning(f"[ResilientLLMProvider] {name} error, waiting {delay}s")
                        time.sleep(delay)
        
        step_logger.error(f"[ResilientLLMProvider] All providers failed for streaming")
        raise last_error or RuntimeError("All providers failed")
    
    async def agenerate_stream(
        self, 
        messages: List[Message], 
        context: Optional[str] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Async stream generate with fallback."""
        providers = [
            (self._main_provider, "Main", self._main_retries, self._main_delays),
            (self._backup_provider, "Backup", self._backup_retries, self._backup_delays),
            (self._fallback_provider, "Fallback", 1, [0]),
        ]
        
        last_error = None
        
        for provider, name, max_retries, delays in providers:
            for attempt in range(max_retries):
                try:
                    step_logger.info(
                        f"[ResilientLLMProvider] Async streaming with {name} "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    
                    async for item in provider.agenerate_stream(
                        messages, context, system_prompt, **kwargs
                    ):
                        # Check for final response marker
                        if isinstance(item, dict) and "_final_response" in item:
                            item["_final_response"].metadata["provider_used"] = name.lower()
                        yield item
                    
                    # If we get here, streaming succeeded
                    return
                    
                except Exception as e:
                    last_error = e
                    if not _is_retriable_error(e):
                        step_logger.error(f"[ResilientLLMProvider] {name} non-retriable: {e}")
                        break
                    
                    if attempt < max_retries - 1:
                        delay = delays[min(attempt, len(delays) - 1)]
                        step_logger.warning(f"[ResilientLLMProvider] {name} error, waiting {delay}s")
                        await asyncio.sleep(delay)
        
        step_logger.error(f"[ResilientLLMProvider] All providers failed for async streaming")
        raise last_error or RuntimeError("All providers failed")
