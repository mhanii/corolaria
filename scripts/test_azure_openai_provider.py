"""
Test script for AzureOpenAILLMProvider with REAL API calls.
Uses your AZURE_API_KEY from .env.
"""
import sys
import os
import asyncio

# Add project root to path
sys.path.append(os.getcwd())

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from src.ai.llm.azure_openai_provider import AzureOpenAILLMProvider
from src.domain.interfaces.llm_provider import Message


def test_real_generate():
    """Test real generation with Azure OpenAI."""
    print("=" * 60)
    print("Testing REAL Azure OpenAI API call...")
    print("=" * 60)
    
    # Initialize provider (will use AZURE_API_KEY from .env)
    provider = AzureOpenAILLMProvider(
        model="gpt-5-mini",  # Your Azure deployment name
        temperature=1,  # o1 models only support temperature=1
        max_tokens=500
    )
    
    print(f"Provider initialized: model={provider._model}")
    print(f"Endpoint: {provider._azure_endpoint}")
    print(f"API Version: {provider._api_version}")
    print()
    
    # Test simple generation
    messages = [Message(role="user", content="Hola, ¿qué tal? Responde brevemente.")]
    
    print("Sending message: 'Hola, ¿qué tal? Responde brevemente.'")
    print("-" * 40)
    
    response = provider.generate(messages)
    
    print(f"Response: {response.content}")
    print(f"Tokens used: {response.usage}")
    print(f"Finish reason: {response.finish_reason}")
    print()
    
    return provider


def test_real_stream(provider):
    """Test real streaming with Azure OpenAI."""
    print("=" * 60)
    print("Testing REAL Azure OpenAI STREAMING...")
    print("=" * 60)
    
    messages = [Message(role="user", content="Cuéntame un chiste corto.")]
    
    print("Sending message: 'Cuéntame un chiste corto.'")
    print("-" * 40)
    print("Streaming response: ", end="", flush=True)
    
    gen = provider.generate_stream(messages)
    try:
        while True:
            chunk = next(gen)
            if chunk:
                print(chunk, end="", flush=True)
    except StopIteration as e:
        final_response = e.value
    
    print()
    print("-" * 40)
    print(f"Tokens used: {final_response.usage}")
    print()


async def test_real_async_stream(provider):
    """Test real async streaming with Azure OpenAI."""
    print("=" * 60)
    print("Testing REAL Azure OpenAI ASYNC STREAMING...")
    print("=" * 60)
    
    messages = [Message(role="user", content="Dame 3 consejos breves para programar mejor.")]
    
    print("Sending message: 'Dame 3 consejos breves para programar mejor.'")
    print("-" * 40)
    print("Async streaming response:")
    
    async for item in provider.agenerate_stream(messages):
        if isinstance(item, dict) and "_final_response" in item:
            final_response = item["_final_response"]
            print()
            print("-" * 40)
            print(f"Tokens used: {final_response.usage}")
        else:
            print(item, end="", flush=True)
    
    print()


def test_with_context(provider):
    """Test generation with RAG context."""
    print("=" * 60)
    print("Testing with CONTEXT injection...")
    print("=" * 60)
    
    context = """
    Artículo 1. El Derecho a la Vida.
    Toda persona tiene derecho a que se respete su vida.
    
    Artículo 2. El Derecho a la Libertad.
    Toda persona tiene derecho a la libertad y a la seguridad personales.
    """
    
    messages = [Message(role="user", content="¿Qué dice el artículo 1?")]
    
    print("Context provided: Articles about Rights")
    print("Question: '¿Qué dice el artículo 1?'")
    print("-" * 40)
    
    response = provider.generate(messages, context=context)
    
    print(f"Response: {response.content}")
    print(f"Tokens used: {response.usage}")
    print()


if __name__ == "__main__":
    try:
        provider = test_real_generate()
        test_real_stream(provider)
        asyncio.run(test_real_async_stream(provider))
        test_with_context(provider)
        
        print("=" * 60)
        print("ALL REAL API TESTS COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
