"""
LangChain LLM Factory for Agents.

Creates LangChain-compatible chat models for use with LangGraph's 
create_react_agent and other LangChain integrations.

Supports configurable providers (Gemini, OpenAI, Azure OpenAI) loaded from config.
"""
import os
from typing import Optional

from src.config import get_agent_config, get_llm_config
from src.utils.logger import step_logger


def create_langchain_llm(
    provider: str = None,
    model: str = None,
    temperature: float = None,
    max_retries: int = 6
):
    """
    Create a LangChain chat model for agents.
    
    Args:
        provider: LLM provider (gemini | openai | azure_openai). Defaults to agent config.
        model: Model/deployment name. Defaults to agent config.
        temperature: Sampling temperature. Defaults to agent config.
        max_retries: Maximum retries for transient errors.
        
    Returns:
        LangChain BaseChatModel instance
        
    Raises:
        ValueError: If provider is unknown or dependencies missing
    """
    # Load config defaults
    agent_config = get_agent_config()
    llm_config = get_llm_config()
    
    provider = provider or agent_config.get("provider") or llm_config.get("provider", "gemini")
    provider_lower = provider.lower()
    
    model = model or agent_config.get("model") or agent_config.get("deployment") or llm_config.get("model")
    temperature = temperature if temperature is not None else agent_config.get("temperature", 0.3)
    
    step_logger.info(f"[LangChainFactory] Creating LLM: provider={provider_lower}, model={model}")
    
    if provider_lower == "gemini":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError:
            raise ValueError(
                "Gemini provider requires 'langchain-google-genai' package. "
                "Install with: pip install langchain-google-genai"
            )
        
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is required for Gemini")
        
        llm = ChatGoogleGenerativeAI(
            model=model or "gemini-2.0-flash",
            google_api_key=api_key,
            temperature=temperature,
            max_retries=max_retries
        )
        
        step_logger.info(f"[LangChainFactory] Created ChatGoogleGenerativeAI: {model}")
        return llm
    
    elif provider_lower == "azure_openai":
        try:
            from langchain_openai import AzureChatOpenAI
        except ImportError:
            raise ValueError(
                "Azure OpenAI provider requires 'langchain-openai' package. "
                "Install with: pip install langchain-openai"
            )
        
        api_key = os.getenv("AZURE_API_KEY")
        azure_endpoint = os.getenv(
            "AZURE_OPENAI_ENDPOINT",
            "https://moham-mj4y5l2w-eastus2.cognitiveservices.azure.com/"
        )
        api_version = agent_config.get("azure_api_version") or "2024-12-01-preview"
        deployment = model or agent_config.get("deployment") or "gpt-5-mini"
        
        if not api_key:
            raise ValueError("AZURE_API_KEY environment variable is required for Azure OpenAI")
        
        llm = AzureChatOpenAI(
            azure_deployment=deployment,
            azure_endpoint=azure_endpoint,
            api_key=api_key,
            api_version=api_version,
            temperature=temperature,
            max_retries=max_retries
        )
        
        step_logger.info(
            f"[LangChainFactory] Created AzureChatOpenAI: deployment={deployment}, "
            f"endpoint={azure_endpoint}"
        )
        return llm
    
    elif provider_lower == "openai":
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            raise ValueError(
                "OpenAI provider requires 'langchain-openai' package. "
                "Install with: pip install langchain-openai"
            )
        
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required for OpenAI")
        
        llm = ChatOpenAI(
            model=model or "gpt-4o",
            api_key=api_key,
            temperature=temperature,
            max_retries=max_retries
        )
        
        step_logger.info(f"[LangChainFactory] Created ChatOpenAI: {model}")
        return llm
    
    else:
        available = ["gemini", "openai", "azure_openai"]
        raise ValueError(f"Unknown agent provider: '{provider}'. Available: {available}")
