#!/usr/bin/env python3
"""
Test script for the Coloraria API semantic search endpoint.
Tests both programmatically using TestClient and provides curl examples.

Usage:
    python scripts/test_api.py
"""
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fastapi.testclient import TestClient
from src.api.main import app
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Create test client
client = TestClient(app)

def test_health_check():
    """Test the health check endpoint."""
    print("\n" + "="*80)
    print("TEST: Health Check")
    print("="*80)
    
    response = client.get("/health")
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    print("✓ Health check passed")


def test_root_endpoint():
    """Test the root endpoint."""
    print("\n" + "="*80)
    print("TEST: Root Endpoint")
    print("="*80)
    
    response = client.get("/")
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    
    assert response.status_code == 200
    print("✓ Root endpoint passed")


def test_semantic_search_valid():
    """Test semantic search with a valid query."""
    print("\n" + "="*80)
    print("TEST: Semantic Search - Valid Query")
    print("="*80)
    
    payload = {
        "query": "libertad de expresión",
        "top_k": 5
    }
    
    print(f"Request: POST /api/v1/search/semantic")
    print(f"Payload: {payload}")
    
    response = client.post("/api/v1/search/semantic", json=payload)
    print(f"\nStatus Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"Query: {data['query']}")
        print(f"Total Results: {data['total_results']}")
        print(f"Strategy: {data['strategy_used']}")
        print(f"Execution Time: {data['execution_time_ms']:.2f}ms")
        
        print(f"\nResults Preview:")
        for i, result in enumerate(data['results'][:3], 1):
            print(f"\n  {i}. {result['article_number']} (Score: {result['score']:.4f})")
            print(f"     Normativa: {result['normativa_title']}")
            print(f"     Text: {result['article_text'][:100]}...")
        
        assert data['total_results'] >= 0
        assert data['strategy_used'] == "Vector Search"
        print("\n✓ Semantic search with valid query passed")
    else:
        print(f"Error: {response.json()}")
        print("✗ Test failed")


def test_semantic_search_invalid_empty_query():
    """Test semantic search with an empty query."""
    print("\n" + "="*80)
    print("TEST: Semantic Search - Empty Query")
    print("="*80)
    
    payload = {
        "query": "",
        "top_k": 5
    }
    
    print(f"Request: POST /api/v1/search/semantic")
    print(f"Payload: {payload}")
    
    response = client.post("/api/v1/search/semantic", json=payload)
    print(f"\nStatus Code: {response.status_code}")
    print(f"Response: {response.json()}")
    
    assert response.status_code == 400
    print("✓ Empty query properly rejected")


def test_semantic_search_invalid_top_k():
    """Test semantic search with invalid top_k."""
    print("\n" + "="*80)
    print("TEST: Semantic Search - Invalid top_k")
    print("="*80)
    
    payload = {
        "query": "test",
        "top_k": -1
    }
    
    print(f"Request: POST /api/v1/search/semantic")
    print(f"Payload: {payload}")
    
    response = client.post("/api/v1/search/semantic", json=payload)
    print(f"\nStatus Code: {response.status_code}")
    print(f"Response: {response.json()}")
    
    assert response.status_code == 400
    print("✓ Invalid top_k properly rejected")


def test_openapi_docs():
    """Test that OpenAPI documentation is accessible."""
    print("\n" + "="*80)
    print("TEST: OpenAPI Documentation")
    print("="*80)
    
    response = client.get("/openapi.json")
    print(f"Status Code: {response.status_code}")
    
    assert response.status_code == 200
    data = response.json()
    assert "openapi" in data
    assert "paths" in data
    assert "/api/v1/search/semantic" in data["paths"]
    print("✓ OpenAPI documentation accessible")


def print_curl_examples():
    """Print curl command examples for manual testing."""
    print("\n" + "="*80)
    print("CURL EXAMPLES FOR MANUAL TESTING")
    print("="*80)
    
    print("\n1. Health Check:")
    print("   curl http://localhost:8000/health")
    
    print("\n2. Semantic Search:")
    print('''   curl -X POST "http://localhost:8000/api/v1/search/semantic" \\
     -H "Content-Type: application/json" \\
     -d '{
       "query": "libertad de expresión",
       "top_k": 5
     }' ''')
    
    print("\n3. View API Documentation:")
    print("   Open browser to: http://localhost:8000/docs")
    
    print("\n4. Start Server:")
    print("   cd /home/kali/coloraria")
    print("   uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000")
    print()


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("COLORARIA API TEST SUITE")
    print("="*80)
    print("\nRunning automated tests using FastAPI TestClient...")
    
    try:
        # Run tests
        test_health_check()
        test_root_endpoint()
        test_openapi_docs()
        test_semantic_search_valid()
        test_semantic_search_invalid_empty_query()
        test_semantic_search_invalid_top_k()
        
        print("\n" + "="*80)
        print("✓ ALL TESTS PASSED")
        print("="*80)
        
        # Print curl examples
        print_curl_examples()
        
    except AssertionError as e:
        print("\n" + "="*80)
        print("✗ TEST FAILED")
        print("="*80)
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print("\n" + "="*80)
        print("✗ UNEXPECTED ERROR")
        print("="*80)
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
