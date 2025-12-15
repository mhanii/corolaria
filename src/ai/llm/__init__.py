"""
LLM Module.
Provides language model integrations for chat completions.
"""
from src.ai.llm.gemini_provider import GeminiLLMProvider
from src.ai.llm.factory import LLMFactory

# Lazy import for optional providers
def get_azure_openai_provider():
    """Lazy import for Azure OpenAI provider."""
    from src.ai.llm.azure_openai_provider import AzureOpenAILLMProvider
    return AzureOpenAILLMProvider

def get_resilient_provider():
    """Lazy import for Resilient provider."""
    from src.ai.llm.resilient_provider import ResilientLLMProvider
    return ResilientLLMProvider

__all__ = ["GeminiLLMProvider", "LLMFactory", "get_azure_openai_provider", "get_resilient_provider"]
