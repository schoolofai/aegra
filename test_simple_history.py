#!/usr/bin/env python3
"""
Simple test to debug the history endpoint 500 error
"""

import asyncio
import httpx
import json

async def test_simple_history():
    """Simple test to debug the history endpoint"""
    
    print("🔍 Simple History Endpoint Debug Test")
    print("=" * 40)
    
    try:
        # Test 1: Simple POST request to see if endpoint is reachable
        print("\n1️⃣ Testing basic POST request...")
        
        async with httpx.AsyncClient() as client:
            # Create a thread first
            thread_response = await client.post(
                "http://localhost:8000/v1/threads",
                headers={
                    "Authorization": "Bearer test-token",
                    "Content-Type": "application/json"
                },
                json={"metadata": {"test": True}}
            )
            
            if thread_response.status_code != 200:
                print(f"❌ Failed to create thread: {thread_response.status_code}")
                print(thread_response.text)
                return False
            
            thread = thread_response.json()
            thread_id = thread["thread_id"]
            print(f"✅ Thread created: {thread_id}")
            
            # Test history endpoint with minimal payload
            print(f"\n2️⃣ Testing history endpoint for thread: {thread_id}")
            
            history_response = await client.post(
                f"http://localhost:8000/v1/threads/{thread_id}/history",
                headers={
                    "Authorization": "Bearer test-token",
                    "Content-Type": "application/json"
                },
                json={"limit": 10}
            )
            
            print(f"📊 Response status: {history_response.status_code}")
            print(f"📊 Response headers: {dict(history_response.headers)}")
            
            if history_response.status_code == 200:
                history = history_response.json()
                print(f"✅ History endpoint works! Got {len(history)} checkpoints")
                if history:
                    print(f"   First checkpoint: {history[0]}")
                return True
            else:
                print(f"❌ History endpoint failed: {history_response.status_code}")
                print(f"   Response: {history_response.text}")
                return False
                
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    asyncio.run(test_simple_history()) 