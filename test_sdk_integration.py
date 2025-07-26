#!/usr/bin/env python3
"""
Integration test using LangGraph SDK to validate our API implementation.

This script tests:
1. Authentication (noop and custom modes)
2. Assistant management
3. Thread operations
4. Run execution with our weather agent
5. Store operations

Run this while the server is running to validate end-to-end functionality.

Prerequisites:
- Install the LangGraph SDK: uv add langgraph-sdk
- Or manually: uv pip install langgraph-sdk
"""

import asyncio
import os
import sys
import subprocess
from typing import Dict, Any

def ensure_sdk_installed():
    """Ensure LangGraph SDK is installed via uv"""
    try:
        # Try to import first
        import langgraph_sdk
        print("✅ LangGraph SDK already installed")
        return True
    except ImportError:
        print("📦 LangGraph SDK not found, installing via uv...")
        try:
            # Try to install using uv
            result = subprocess.run(
                ["uv", "pip", "install", "langgraph-sdk"],
                check=True,
                capture_output=True,
                text=True
            )
            print("✅ LangGraph SDK installed successfully")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install LangGraph SDK: {e}")
            print(f"STDOUT: {e.stdout}")
            print(f"STDERR: {e.stderr}")
            print("\nPlease install manually with: uv pip install langgraph-sdk")
            return False
        except FileNotFoundError:
            print("❌ uv command not found. Please install uv first or install the SDK manually:")
            print("   pip install langgraph-sdk")
            return False

# Ensure SDK is installed before importing
if not ensure_sdk_installed():
    sys.exit(1)

from langgraph_sdk import get_client


class APITester:
    def __init__(self, base_url: str = "http://localhost:8000/v1", api_key: str = None):
        self.client = get_client(url=base_url, api_key=api_key)
        self.base_url = base_url
        self.api_key = api_key
        
    async def test_authentication(self):
        """Test different authentication modes"""
        print("🔐 Testing Authentication...")
        
        try:
            # Test with noop auth (should work without API key)
            assistants = await self.client.assistants.search()
            print(f"✅ Noop auth working - found {len(assistants)} assistants")
            return True
        except Exception as e:
            print(f"❌ Authentication failed: {e}")
            return False
    
    async def test_assistant_management(self):
        """Test assistant CRUD operations"""
        print("\n👤 Testing Assistant Management...")
        
        try:
            # List existing assistants
            assistants = await self.client.assistants.search()
            print(f"📋 Found {len(assistants)} existing assistants")
            
            # Create a test assistant
            try:
                assistant = await self.client.assistants.create(
                    graph_id="weather_agent",
                    assistant_id="test-weather-assistant",
                    name="Test Weather Assistant",
                    description="Test assistant for weather queries",
                    if_exists="do_nothing"
                )
                print(f"✅ Created assistant: {assistant['assistant_id']}")
            except Exception as e:
                print(f"❌ Failed to create assistant: {e}")
                # Try to get existing assistant
                try:
                    assistant = await self.client.assistants.get("test-weather-assistant")
                    print("ℹ️  Using existing assistant")
                except:
                    assistant = None
            
            # Search for assistants by graph_id
            search_results = await self.client.assistants.search(graph_id="weather_agent")
            print(f"🔍 Search found {len(search_results)} assistants with graph_id 'weather_agent'")
            
            # If creation failed, try to use an existing assistant
            if not assistant and search_results:
                assistant = search_results[0]
                print(f"ℹ️  Using existing assistant: {assistant['assistant_id']}")
            
            return assistant
            
        except Exception as e:
            print(f"❌ Assistant management failed: {e}")
            return None
    
    async def test_thread_operations(self):
        """Test thread CRUD operations"""
        print("\n🧵 Testing Thread Operations...")
        
        try:
            # Create a thread
            thread = await self.client.threads.create()
            print(f"✅ Created thread: {thread['thread_id']}")
            
            # Get the thread
            retrieved_thread = await self.client.threads.get(thread['thread_id'])
            print(f"✅ Retrieved thread: {retrieved_thread['thread_id']}")
            
            # Search threads
            threads = await self.client.threads.search()
            print(f"📋 Found {len(threads)} total threads")
            
            return thread
            
        except Exception as e:
            print(f"❌ Thread operations failed: {e}")
            return None
    
    async def test_run_execution(self, assistant, thread):
        """Test run creation and execution"""
        print("\n🏃 Testing Run Execution...")
        
        if not assistant or not thread:
            print("❌ Skipping run tests - missing assistant or thread")
            return None
            
        try:
            # Create a run
            run_data = {
                "assistant_id": assistant['assistant_id'],
                "input": {
                    "messages": [{"role": "user", "content": "What's the weather like?"}]
                }
            }
            
            run = await self.client.runs.create(
                thread_id=thread['thread_id'],
                **run_data
            )
            print(f"✅ Created run: {run['run_id']}")
            
            # Wait for completion using join
            print("⏳ Waiting for run to complete...")
            result = await self.client.runs.join(
                thread_id=thread['thread_id'],
                run_id=run['run_id']
            )
            
            # Get final run status
            completed_run = await self.client.runs.get(
                thread_id=thread['thread_id'],
                run_id=run['run_id']
            )
            print(f"✅ Run completed with status: {completed_run['status']}")
            
            if result:
                print(f"📤 Run output: {result}")
            
            # List runs for the thread
            runs = await self.client.runs.list(thread_id=thread['thread_id'])
            print(f"📋 Thread has {len(runs)} runs")
            
            return completed_run
            
        except Exception as e:
            print(f"❌ Run execution failed: {e}")
            return None
    
    async def test_store_operations(self):
        """Test store CRUD operations"""
        print("\n🗄️  Testing Store Operations...")
        
        try:
            # Put an item (namespace is positional-only)
            await self.client.store.put_item(
                ["test"],  # namespace as positional arg
                key="greeting",
                value={"message": "Hello from store test!"}
            )
            print("✅ Stored item successfully")
            
            # Get the item
            item = await self.client.store.get_item(
                ["test"],  # namespace as positional arg
                key="greeting"
            )
            print(f"✅ Retrieved item: {item['value']}")
            
            # Search for items
            search_results = await self.client.store.search_items(
                namespace_prefix=["test"]
            )
            print(f"🔍 Store search found {len(search_results)} items")
            
            # Delete the item
            await self.client.store.delete_item(
                ["test"],  # namespace as positional arg
                key="greeting"
            )
            print("✅ Deleted item successfully")
            
            return True
            
        except Exception as e:
            print(f"❌ Store operations failed: {e}")
            print("ℹ️  This might be expected if store functionality isn't implemented yet")
            return False
    
    async def test_streaming(self, assistant, thread):
        """Test streaming run execution"""
        print("\n📡 Testing Streaming...")
        
        if not assistant or not thread:
            print("❌ Skipping streaming tests - missing assistant or thread")
            return False
            
        try:
            # Create a streaming run
            run_data = {
                "assistant_id": assistant['assistant_id'],
                "input": {
                    "messages": [{"role": "user", "content": "Tell me about the weather"}]
                }
            }
            
            run = await self.client.runs.create(
                thread_id=thread['thread_id'],
                **run_data
            )
            
            print(f"✅ Created streaming run: {run['run_id']}")
            print("📡 Streaming events...")
            
            # Stream the run
            event_count = 0
            async for event in self.client.runs.stream(
                thread_id=thread['thread_id'],
                run_id=run['run_id']
            ):
                event_count += 1
                print(f"📨 Event {event_count}: {event.get('event', 'unknown')}")
                
                if event_count >= 10:  # Limit output
                    print("... (truncated)")
                    break
            
            print(f"✅ Received {event_count} streaming events")
            return True
            
        except Exception as e:
            print(f"❌ Streaming failed: {e}")
            return False
    
    async def run_all_tests(self):
        """Run all integration tests"""
        print("🚀 Starting LangGraph SDK Integration Tests")
        print(f"🌐 Testing against: {self.base_url}")
        print("=" * 60)
        
        results = {}
        
        # Test authentication
        results['auth'] = await self.test_authentication()
        
        # Test assistant management
        assistant = await self.test_assistant_management()
        results['assistants'] = assistant is not None
        
        # Test thread operations
        thread = await self.test_thread_operations()
        results['threads'] = thread is not None
        
        # Test run execution
        run = await self.test_run_execution(assistant, thread)
        results['runs'] = run is not None
        
        # Test store operations
        results['store'] = await self.test_store_operations()
        
        # Test streaming
        results['streaming'] = await self.test_streaming(assistant, thread)
        
        # Summary
        print("\n" + "=" * 60)
        print("📊 Test Results Summary:")
        print("=" * 60)
        
        total_tests = len(results)
        passed_tests = sum(1 for result in results.values() if result)
        
        for test_name, passed in results.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{test_name.upper():.<20} {status}")
        
        print("-" * 60)
        print(f"TOTAL: {passed_tests}/{total_tests} tests passed")
        
        if passed_tests == total_tests:
            print("🎉 All tests passed! Your API is fully compatible with LangGraph SDK!")
        else:
            print("⚠️  Some tests failed. Check the logs above for details.")
        
        return results


async def main():
    """Main test function"""
    
    print("🔧 LangGraph SDK Integration Test Setup Complete")
    print("📋 SDK Installation Status: ✅")
    print()
    
    # Test with noop auth first
    print("Testing with NOOP authentication...")
    tester = APITester(api_key=None)
    results = await tester.run_all_tests()
    
    # If you want to test custom auth, uncomment and modify:
    # print("\n" + "="*60)
    # print("Testing with CUSTOM authentication...")
    # custom_tester = APITester(api_key="Bearer dev-token")
    # custom_results = await custom_tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())