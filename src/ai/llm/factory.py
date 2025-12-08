"""
LLM Provider Factory.
Creates LLM providers based on configuration for easy swapping.
"""
from typing import Optional
from src.domain.interfaces.llm_provider import LLMProvider
from src.ai.llm.gemini_provider import GeminiLLMProvider


class LLMFactory:
    """Factory for creating LLM providers with dependency injection."""
    
    @staticmethod
    def create(
        provider: str = "gemini",
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 8192,
        **kwargs
    ) -> LLMProvider:
        """
        Create an LLM provider instance.
        
        Args:
            provider: Provider name ("gemini", "openai", "anthropic")
            model: Model identifier (provider-specific)
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Provider-specific parameters
            
        Returns:
            LLMProvider instance
            
        Raises:
            ValueError: If provider is unknown
        """
        provider_lower = provider.lower()
        
        if provider_lower == "gemini":
            return GeminiLLMProvider(
                model=model or "gemini-2.5-flash",
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=kwargs.get("api_key")
            )
        
        elif provider_lower == "openai":
            # Lazy import to avoid dependency if not used
            try:
                from src.ai.llm.openai_provider import OpenAILLMProvider
                return OpenAILLMProvider(
                    model=model or "gpt-4o",
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
                    model=model or "claude-3-5-sonnet-20241022",
                    temperature=temperature,
                    max_tokens=max_tokens,
                    api_key=kwargs.get("api_key")
                )
            except ImportError:
                raise ValueError("Anthropic provider requires 'anthropic' package. Install with: pip install anthropic")
        
        else:
            available = ["gemini", "openai", "anthropic"]
            raise ValueError(f"Unknown LLM provider: '{provider}'. Available: {available}")
