#!/usr/bin/env python3
"""
Quick test script for admin API endpoints.
Run: PYTHONPATH=. venv/bin/python test_admin_api.py
"""

import httpx
import asyncio
import json

BASE_URL = "http://localhost:8001/api/v1"


async def test_endpoints():
    """Test various admin API endpoints."""
    async with httpx.AsyncClient() as client:
        print("Testing Admin API endpoints...")
        print("=" * 50)

        # Test stats
        print("📊 Pipeline Stats:")
        resp = await client.get(f"{BASE_URL}/pipeline/stats")
        if resp.status_code == 200:
            stats = resp.json()
            print(f"  Products: {stats['products']}")
            print(f"  Categories: {stats['categories']}")
            print(f"  Documents: {stats['documents']}")
            print(f"  Chunks: {stats['chunks']}")
            print(f"  Index versions: {stats['index_versions']}")
        print()

        # Test products list
        print("🛠️  Products (first 3):")
        resp = await client.get(f"{BASE_URL}/products/?page=1&per_page=3")
        if resp.status_code == 200:
            products = resp.json()
            for item in products['items']:
                print(f"  {item['id']}: {item['name']} (chunks: {item['chunks_count']})")
        print()

        # Test categories tree
        print("📂 Categories tree:")
        resp = await client.get(f"{BASE_URL}/categories/tree")
        if resp.status_code == 200:
            categories = resp.json()
            for cat in categories[:3]:  # First 3 categories
                print(f"  {cat['id']}: {cat['name']} ({cat['products_count']} products)")
        print()

        # Test chunks
        print("📄 Recent chunks (first 3):")
        resp = await client.get(f"{BASE_URL}/chunks/?page=1&per_page=3")
        if resp.status_code == 200:
            chunks = resp.json()
            for chunk in chunks['items']:
                preview = chunk['chunk_text_preview'][:50] + "..."
                print(f"  {chunk['id']}: {preview} (tokens: {chunk['token_count']})")
        print()

        # Test FAQ
        print("❓ Company FAQ (first 100 chars):")
        resp = await client.get(f"{BASE_URL}/faq/company")
        if resp.status_code == 200:
            faq = resp.json()
            print(f"  {faq['content'][:100]}...")
        print()

        print("✅ All tests completed!")


if __name__ == "__main__":
    try:
        asyncio.run(test_endpoints())
    except httpx.ConnectError:
        print("❌ Server not running. Start with:")
        print("PYTHONPATH=. venv/bin/uvicorn admin.main:app --host 0.0.0.0 --port 8001")