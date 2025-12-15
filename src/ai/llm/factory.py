"""
LLM Provider Factory.
Creates LLM providers based on configuration for easy swapping.
"""
from typing import Optional
from src.domain.interfaces.llm_provider import LLMProvider
from src.ai.llm.gemini_provider import GeminiLLMProvider
from src.config import get_llm_config


class LLMFactory:
    """Factory for creating LLM providers with dependency injection."""
    
    @staticmethod
    def create(
        provider: str = None,
        model: Optional[str] = None,
        temperature: float = None,
        max_tokens: int = None,
        **kwargs
    ) -> LLMProvider:
        """
        Create an LLM provider instance.
        
        Args:
            provider: Provider name (defaults to config)
            model: Model identifier (defaults to config)
            temperature: Sampling temperature (defaults to config)
            max_tokens: Maximum tokens to generate (defaults to config)
            **kwargs: Provider-specific parameters
            
        Returns:
            LLMProvider instance
            
        Raises:
            ValueError: If provider is unknown
        """
        # Load defaults from config
        config = get_llm_config()
        
        provider = provider or config.get("provider", "gemini")
        provider_lower = provider.lower()
        
        # Use config defaults if parameters are not provided
        if model is None and provider_lower == config.get("provider"):
            model = config.get("model")
            
        temperature = temperature if temperature is not None else config.get("temperature", 0.3)
        max_tokens = max_tokens if max_tokens is not None else config.get("max_tokens", 8192)
        
        if provider_lower == "gemini":
            return GeminiLLMProvider(
                model=model,  # Provider handles None -> default logic if needed, but we pass config val
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=kwargs.get("api_key")
            )
        
        elif provider_lower == "openai":
            # Lazy import to avoid dependency if not used
            try:
                from src.ai.llm.openai_provider import OpenAILLMProvider
                return OpenAILLMProvider(
                    model=model or "gpt-4o", # Fallback if not configured
                    temperature=temperature,
                    max_tokens=max_tokens,
                    api_key=kwargs.get("api_key")
                )
            except ImportError:
                raise ValueError("OpenAI provider requires 'openai' package. Install with: pip install openai")
        
        elif provider_lower == "anthropic":
            # Lazy import to avoid dependency if not used
            try:
                from src.ai.llm.anthropic_provider import AnthropicLLMProvider
                return AnthropicLLMProvider(
                    model=model or "claude-3-5-sonnet-20241022", # Fallback if not configured
                    temperature=temperature,
                    max_tokens=max_tokens,
                    api_key=kwargs.get("api_key")
                )
            except ImportError:
                raise ValueError("Anthropic provider requires 'anthropic' package. Install with: pip install anthropic")
        
        elif provider_lower == "azure_openai":
            # Lazy import to avoid dependency if not used
            try:
                from src.ai.llm.azure_openai_provider import AzureOpenAILLMProvider
                return AzureOpenAILLMProvider(
                    model=model or "gpt-4o",  # Fallback deployment name
                    temperature=temperature,
                    max_tokens=max_tokens,
                    api_key=kwargs.get("api_key"),
                    azure_endpoint=kwargs.get("azure_endpoint"),
                    api_version=kwargs.get("api_version")
                )
            except ImportError:
                raise ValueError("Azure OpenAI provider requires 'openai' package. Install with: pip install openai")
        
        else:
            available = ["gemini", "openai", "anthropic", "azure_openai"]
            raise ValueError(f"Unknown LLM provider: '{provider}'. Available: {available}")
