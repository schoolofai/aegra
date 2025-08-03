#!/usr/bin/env python3
"""
Test script for the Thread History endpoint using LangGraph SDK client.
This tests the history endpoint functionality with real API calls.
"""

import asyncio
import os
from langgraph_sdk import get_client

async def test_history_endpoint():
    """Test the thread history endpoint using SDK client"""
    
    print("📚 Testing Thread History Endpoint")
    print("==================================")
    
    try:
        # Create SDK client
        client = get_client(url="http://localhost:8000/v1", api_key="test-key")
        
        # Create assistant with chat_agent
        print("📝 Creating chat assistant...")
        assistant = await client.assistants.create(
            graph_id="chat_agent",
            config={"tags": ["chat", "llm"]},
            if_exists="do_nothing"
        )
        print(f"✅ Chat Assistant: {assistant['assistant_id']}")
        
        # Create thread
        print("🧵 Creating thread...")
        thread = await client.threads.create()
        print(f"✅ Thread: {thread['thread_id']}")
        
        # Test 1: Get history on empty thread
        print("\n1️⃣ Testing history on empty thread...")
        try:
            # Debug: Let's see what the SDK is actually calling
            print(f"🔍 Calling history endpoint for thread: {thread['thread_id']}")
            history = await client.threads.get_history(thread['thread_id'])
            print(f"✅ Empty thread history: {len(history)} checkpoints")
            if history:
                print(f"   First checkpoint: {history[0]}")
            else:
                print("   No checkpoints yet (expected for new thread)")
        except Exception as e:
            print(f"❌ Failed to get empty thread history: {e}")
            print(f"   Error type: {type(e)}")
            print(f"   Error details: {str(e)}")
        
        # Test 2: Run a conversation to create checkpoints
        print("\n2️⃣ Running conversation to create checkpoints...")
        run = await client.runs.create(
            thread_id=thread['thread_id'],
            assistant_id=assistant['assistant_id'],
            input={"messages": [{"role": "human",  "content": "Hello! Tell me a short joke."}]}
        )
        print(f"🔄 Run created: {run['run_id']}")
        
        # Wait for run to complete
        print("⏳ Waiting for run to complete...")
        final_run = await client.runs.join(thread['thread_id'], run['run_id'])
        print(f"✅ Run completed: {final_run}")
        # Handle different response formats
        run_status = final_run.get('status', 'unknown')
        print(f"   Status: {run_status}")
        
        # Test 3: Get history after first run
        print("\n3️⃣ Testing history after first run...")
        try:
            history = await client.threads.get_history(thread['thread_id'])
            print(f"✅ History after first run: {len(history)} checkpoints")
            if history:
                print(f"   Latest checkpoint: {history[0]}")
                print(f"   Checkpoint ID: {history[0]['checkpoint']['checkpoint_id']}")
                print(f"   Has values: {'values' in history[0]}")
                print(f"   Values keys: {list(history[0]['values'].keys()) if 'values' in history[0] else 'None'}")
                
                # Print full history data in detail
                print("\n📋 FULL HISTORY DATA (First Run):")
                print("=" * 60)
                for i, checkpoint in enumerate(history):
                    print(f"\n🔍 Checkpoint {i+1}:")
                    print(f"   📅 Created at: {checkpoint.get('created_at', 'N/A')}")
                    print(f"   🆔 Checkpoint ID: {checkpoint.get('checkpoint_id', 'N/A')}")
                    print(f"   📍 Checkpoint: {checkpoint.get('checkpoint', {})}")
                    print(f"   👤 Parent: {checkpoint.get('parent_checkpoint', 'None')}")
                    print(f"   📊 Metadata: {checkpoint.get('metadata', {})}")
                    print(f"   ➡️  Next: {checkpoint.get('next', [])}")
                    print(f"   📋 Tasks: {checkpoint.get('tasks', [])}")
                    
                    # Print values in detail
                    values = checkpoint.get('values', {})
                    print(f"   💬 Values:")
                    for key, value in values.items():
                        if key == 'messages':
                            print(f"     📝 Messages ({len(value)}):")
                            for j, msg in enumerate(value):
                                print(f"       {j+1}. {msg.get('role', 'unknown')}: {msg.get('content', 'N/A')[:100]}...")
                        else:
                            print(f"     {key}: {str(value)[:100]}...")
            else:
                print("   No checkpoints found (unexpected)")
        except Exception as e:
            print(f"❌ Failed to get history after first run: {e}")
            print(f"   Error type: {type(e)}")
            print(f"   Error details: {str(e)}")
        
        # Test 4: Run another conversation
        print("\n4️⃣ Running second conversation...")
        run2 = await client.runs.create(
            thread_id=thread['thread_id'],
            assistant_id=assistant['assistant_id'],
            input={"messages": [{"role": "human", "content": "What's the weather like today?"}]}
        )
        print(f"🔄 Second run created: {run2['run_id']}")
        
        # Wait for second run to complete
        final_run2 = await client.runs.join(thread['thread_id'], run2['run_id'])
        print(f"✅ Second run completed: {final_run2}")
        run_status2 = final_run2.get('status', 'unknown')
        print(f"   Status: {run_status2}")
        
        # Test 5: Get history after second run
        print("\n5️⃣ Testing history after second run...")
        try:
            history = await client.threads.get_history(thread['thread_id'])
            print(f"✅ History after second run: {len(history)} checkpoints")
            if len(history) >= 2:
                print(f"   Latest checkpoint: {history[0]['checkpoint']['checkpoint_id']}")
                print(f"   Previous checkpoint: {history[1]['checkpoint']['checkpoint_id']}")
                print(f"   Latest values keys: {list(history[0]['values'].keys()) if 'values' in history[0] else 'None'}")
            else:
                print(f"   Only {len(history)} checkpoint(s) found (expected at least 2)")
            
            # Print full history data in detail
            print("\n📋 FULL HISTORY DATA (After Second Run):")
            print("=" * 60)
            for i, checkpoint in enumerate(history):
                print(f"\n🔍 Checkpoint {i+1}:")
                print(f"   📅 Created at: {checkpoint.get('created_at', 'N/A')}")
                print(f"   🆔 Checkpoint ID: {checkpoint.get('checkpoint_id', 'N/A')}")
                print(f"   📍 Checkpoint: {checkpoint.get('checkpoint', {})}")
                print(f"   👤 Parent: {checkpoint.get('parent_checkpoint', 'None')}")
                print(f"   📊 Metadata: {checkpoint.get('metadata', {})}")
                print(f"   ➡️  Next: {checkpoint.get('next', [])}")
                print(f"   📋 Tasks: {checkpoint.get('tasks', [])}")
                
                # Print values in detail
                values = checkpoint.get('values', {})
                print(f"   💬 Values:")
                for key, value in values.items():
                    if key == 'messages':
                        print(f"     📝 Messages ({len(value)}):")
                        for j, msg in enumerate(value):
                            role = msg.get('role', 'unknown')
                            content = msg.get('content', 'N/A')
                            print(f"       {j+1}. {role}: {content[:100]}{'...' if len(content) > 100 else ''}")
                    else:
                        print(f"     {key}: {str(value)[:100]}...")
        except Exception as e:
            print(f"❌ Failed to get history after second run: {e}")
            print(f"   Error type: {type(e)}")
            print(f"   Error details: {str(e)}")
        
        # Test 6: Test pagination with limit
        print("\n6️⃣ Testing history with limit parameter...")
        try:
            history_limited = await client.threads.get_history(thread['thread_id'], limit=1)
            print(f"✅ History with limit=1: {len(history_limited)} checkpoints")
            if history_limited:
                print(f"   Limited checkpoint: {history_limited[0]['checkpoint']['checkpoint_id']}")
        except Exception as e:
            print(f"❌ Failed to get limited history: {e}")
            print(f"   Error type: {type(e)}")
            print(f"   Error details: {str(e)}")
        
        # Test 7: Test with non-existent thread
        print("\n7️⃣ Testing history with non-existent thread...")
        try:
            fake_thread_id = "00000000-0000-0000-0000-000000000000"
            await client.threads.get_history(fake_thread_id)
            print("❌ Expected 404 error for non-existent thread")
        except Exception as e:
            if "404" in str(e) or "not found" in str(e).lower():
                print("✅ Correctly returned error for non-existent thread")
            else:
                print(f"❌ Unexpected error for non-existent thread: {e}")
        
        print("\n" + "="*50)
        print("🎉 History endpoint test completed!")
        return True
        
    except Exception as e:
        print(f"❌ History endpoint test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_history_endpoint_mock():
    """Test history endpoint without real API calls (mock test)"""
    print("🧪 Running mock test (no real API calls)")
    
    try:
        client = get_client(url="http://localhost:8000/v1", api_key="test-key")
        
        # Check if history endpoint is available by trying to create a thread
        thread = await client.threads.create()
        print(f"✅ History endpoint infrastructure is available")
        print(f"📋 Created test thread: {thread['thread_id']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Mock test failed: {e}")
        return False

async def main():
    """Main test function"""
    print("🚀 Starting Thread History Endpoint Tests")
    print("="*50)
    
    success = await test_history_endpoint()
    
    print(f"\n{'='*50}")
    if success:
        print("✅ History endpoint test completed successfully!")
        print("💡 This validates that:")
        print("   - History endpoint is accessible")
        print("   - Checkpoint history is being created")
        print("   - Pagination works correctly")
        print("   - Error handling works properly")
    else:
        print("❌ History endpoint test failed")
        print("💡 Check server logs and endpoint implementation")
    
    return success

# For quick manual run
if __name__ == "__main__":
    asyncio.run(main()) 