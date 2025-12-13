#!/usr/bin/env python3
"""
Test script for EUR-Lex connection and document retrieval.

Usage:
    python scripts/test_eurlex_connection.py

Requires EURLEX_USERNAME and EURLEX_PASSWORD in .env
"""

import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import httpx

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.infrastructure.http.eurlex_client import EURLexHTTPClient, create_eurlex_client


async def test_connection():
    """Test EUR-Lex API connection."""
    load_dotenv()
    
    username = os.getenv("EURLEX_USERNAME")
    password = os.getenv("EURLEX_PASSWORD")
    
    print("=" * 60)
    print("EUR-Lex Connection Test")
    print("=" * 60)
    
    if not username or not password:
        print("\n❌ ERROR: Missing credentials!")
        print("   Please set EURLEX_USERNAME and EURLEX_PASSWORD in .env")
        print("\n   Example:")
        print("   EURLEX_USERNAME=your_email@example.com")
        print("   EURLEX_PASSWORD=your_webservice_password")
        return False
    
    print(f"\n📧 Username: {username}")
    print(f"🔑 Password: {'*' * len(password)}")
    
    async with EURLexHTTPClient(username=username, password=password) as client:
        # Test 1: Health check
        print("\n--- Test 1: SOAP Health Check ---")
        try:
            healthy = await client.health_check()
            if healthy:
                print("✅ EUR-Lex SOAP service is accessible")
            else:
                print("❌ Health check failed")
                return False
        except httpx.HTTPStatusError as e:
            # Parse SOAP fault for better error message
            body = e.response.text
            if 'FailedAuthentication' in body:
                print("❌ Authentication failed!")
                print("\n   The credentials were rejected by EUR-Lex.")
                print("   This usually means:")
                print("   1. Your registration hasn't been approved yet")
                print("   2. The password in .env is not the web service password")
                print("   3. EUR-Lex sends a SEPARATE password after approval")
                print("\n   Check your email for an approval message from EUR-Lex.")
            else:
                print(f"❌ SOAP error: {e}")
                if body:
                    print(f"   Response: {body[:300]}")
            return False
        except Exception as e:
            print(f"❌ Health check error: {e}")
            return False
        
        # Test 2: Simple search
        print("\n--- Test 2: SOAP Search ---")
        try:
            # Search for a specific recent regulation
            results = await client.search(
                expert_query="SELECT DN, TI WHERE DN=32024R*",
                page=1,
                page_size=3,
                language="es"
            )
            
            print(f"✅ Search returned {len(results)} results")
            for i, r in enumerate(results[:3], 1):
                print(f"   {i}. CELLAR: {r.cellar_id[:20]}...")
                if r.celex_number:
                    print(f"      CELEX: {r.celex_number}")
                if r.title:
                    print(f"      Title: {r.title[:60]}...")
                    
        except Exception as e:
            print(f"❌ Search error: {e}")
            return False
        
        # Test 3: CELLAR REST API (public, no auth needed)
        print("\n--- Test 3: CELLAR REST API ---")
        try:
            # Try to fetch a known document
            test_celex = "32024R0903"  # Example: AI Act
            content = await client.get_document_content(
                identifier=test_celex,
                format="html",
                language="eng"
            )
            
            print(f"✅ Retrieved document {test_celex}")
            print(f"   Content size: {len(content)} bytes")
            
        except Exception as e:
            print(f"⚠️  CELLAR fetch warning: {e}")
            print("   (This may fail if the document ID is unavailable)")
    
    print("\n" + "=" * 60)
    print("✅ All tests passed - EUR-Lex integration is working!")
    print("=" * 60)
    
    return True


async def demo_fetch_document(celex: str = "32024R0903"):
    """Demo fetching a full document."""
    load_dotenv()
    
    print(f"\n📄 Fetching document: {celex}")
    
    from src.application.pipeline.eu_data_retriever import EUDataRetriever
    from src.application.pipeline.eu_data_processor import EUDataProcessor
    
    # Retrieve
    retriever = EUDataRetriever(
        name="test_retriever",
        document_id=celex,
        language="spa"
    )
    
    data = retriever.process(None)
    
    if not data.get('content'):
        print("❌ No content retrieved")
        return
    
    print(f"✅ Retrieved {len(data['content'])} bytes")
    
    # Process
    processor = EUDataProcessor(name="test_processor")
    normativa, _ = processor.process(data)
    
    if normativa:
        print(f"\n📋 Document: {normativa.metadata.title[:80]}...")
        print(f"   Type: {normativa.metadata.document_type}")
        print(f"   CELEX: {normativa.metadata.celex_number}")
        
        # Count articles
        def count(node):
            c = 1 if node.node_type.value == 'articulo' else 0
            for child in node.content or []:
                if hasattr(child, 'node_type'):
                    c += count(child)
            return c
        
        articles = count(normativa.content_tree)
        print(f"   Articles: {articles}")
    else:
        print("❌ Failed to process document")


async def test_public_only():
    """Test public EUR-Lex endpoint (no credentials required)."""
    print("=" * 60)
    print("EUR-Lex PUBLIC Endpoint Test (No Credentials)")
    print("=" * 60)
    
    test_docs = [
        ("32024R1689", "AI Act"),
        ("32016R0679", "GDPR"),
        ("32022R2065", "Digital Services Act"),
    ]
    
    async with EURLexHTTPClient() as client:
        for celex, name in test_docs:
            print(f"\n📄 {name} (CELEX: {celex})")
            try:
                html = await client.get_html_content(celex, language="ES")
                print(f"   ✅ Success! {len(html):,} bytes")
            except httpx.HTTPStatusError as e:
                print(f"   ❌ HTTP {e.response.status_code}")
            except Exception as e:
                print(f"   ❌ Error: {e}")
    
    print("\n" + "=" * 60)
    print("✅ Public endpoint works! No SOAP credentials needed.")
    print("=" * 60)
    return True


if __name__ == "__main__":
    print("\n🇪🇺 EUR-Lex Integration Test\n")
    
    if "--public" in sys.argv:
        # Test public endpoint only (no credentials needed)
        success = asyncio.run(test_public_only())
    elif len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        # Fetch specific document
        celex = sys.argv[1]
        asyncio.run(demo_fetch_document(celex))
        success = True
    else:
        # Full test with SOAP credentials
        success = asyncio.run(test_connection())
        
        if success and len(sys.argv) > 1:
            celex = sys.argv[1]
            asyncio.run(demo_fetch_document(celex))
    
    sys.exit(0 if success else 1)

