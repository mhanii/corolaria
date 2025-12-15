"""
Test script for configurable AgentCollector LLM provider.
Tests both Gemini and Azure OpenAI providers.
"""
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

# Load environment variables
from dotenv import load_dotenv
load_dotenv()


def test_langchain_factory_gemini():
    """Test LangChain factory creates Gemini LLM."""
    print("=" * 60)
    print("Testing LangChain Factory - Gemini")
    print("=" * 60)
    
    from src.ai.agents.langchain_factory import create_langchain_llm
    
    llm = create_langchain_llm(
        provider="gemini",
        model="gemini-2.0-flash",
        temperature=0.3
    )
    
    print(f"Created: {type(llm).__name__}")
    print(f"Model: {llm.model}")
    print("SUCCESS: Gemini LLM created\n")
    return llm


def test_langchain_factory_azure():
    """Test LangChain factory creates Azure OpenAI LLM."""
    print("=" * 60)
    print("Testing LangChain Factory - Azure OpenAI")
    print("=" * 60)
    
    from src.ai.agents.langchain_factory import create_langchain_llm
    
    llm = create_langchain_llm(
        provider="azure_openai",
        model="gpt-5-mini",
        temperature=1  # o1 models require temp=1
    )
    
    print(f"Created: {type(llm).__name__}")
    print(f"Deployment: {llm.deployment_name}")
    print("SUCCESS: Azure OpenAI LLM created\n")
    return llm


def test_azure_llm_invoke(llm):
    """Test Azure LLM can generate a response."""
    print("=" * 60)
    print("Testing Azure OpenAI LLM Invoke")
    print("=" * 60)
    
    response = llm.invoke("Hola, responde con una sola palabra: OK")
    print(f"Response: {response.content}")
    print("SUCCESS: Azure OpenAI LLM invoked\n")


if __name__ == "__main__":
    try:
        # Test Gemini factory
        gemini_llm = test_langchain_factory_gemini()
        
        # Test Azure OpenAI factory
        azure_llm = test_langchain_factory_azure()
        
        # Test Azure invoke
        test_azure_llm_invoke(azure_llm)
        
        # Test direct OpenAI (skip if no key)
        if os.getenv("OPENAI_API_KEY"):
            print("=" * 60)
            print("Testing LangChain Factory - Direct OpenAI")
            print("=" * 60)
            from src.ai.agents.langchain_factory import create_langchain_llm
            openai_llm = create_langchain_llm(
                provider="openai",
                model="gpt-4o",
                temperature=0.7
            )
            print(f"Created: {type(openai_llm).__name__}")
            print("SUCCESS: Direct OpenAI LLM created\n")
        else:
            print("\nSkipping direct OpenAI test (OPENAI_API_KEY not set)\n")
        
        print("=" * 60)
        print("ALL TESTS PASSED!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
