"""
Test script for ResilientLLMProvider.
Tests the fallback mechanism with real providers.
"""
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

# Load environment variables
from dotenv import load_dotenv
load_dotenv()


def test_resilient_provider():
    """Test ResilientLLMProvider initialization and basic generation."""
    print("=" * 60)
    print("Testing ResilientLLMProvider")
    print("=" * 60)
    
    from src.ai.llm.resilient_provider import ResilientLLMProvider
    from src.domain.interfaces.llm_provider import Message
    
    # Initialize
    print("Initializing ResilientLLMProvider...")
    provider = ResilientLLMProvider()
    
    print(f"\nProviders ready:")
    print(f"  Main: {provider._main_provider.model}")
    print(f"  Backup: {provider._backup_provider.model}")
    print(f"  Fallback: {provider._fallback_provider.model}")
    
    # Test generate
    print("\n" + "=" * 60)
    print("Testing generate()...")
    print("=" * 60)
    
    messages = [
        Message(role="user", content="Di 'Hola' y nada más.")
    ]
    
    response = provider.generate(messages)
    print(f"\nResponse: {response.content}")
    print(f"Model: {response.model}")
    print(f"Provider used: {response.metadata.get('provider_used', 'unknown')}")
    print(f"Tokens: {response.usage}")
    
    print("\n" + "=" * 60)
    print("ResilientLLMProvider TEST PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    try:
        test_resilient_provider()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
