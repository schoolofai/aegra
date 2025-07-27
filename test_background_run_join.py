#!/usr/bin/env python3
"""
Test for background run creation + join_stream pattern
"""

import asyncio
from langgraph_sdk import get_client

async def test_background_run_then_join():
    """Test creating a run in background, then joining its stream"""
    
    print("🧪 Testing Background Run + Join Stream Pattern")
    print("=" * 50)
    
    try:
        client = get_client(url="http://localhost:8000/v1", api_key="test-key")
        
        # Create assistant and thread
        assistant = await client.assistants.create(
            graph_id="chat_agent",
            if_exists="do_nothing"
        )
        thread = await client.threads.create()
        
        print(f"✅ Assistant: {assistant['assistant_id']}")
        print(f"✅ Thread: {thread['thread_id']}")
        
        # Step 1: Create run in background (non-streaming)
        print("\n🚀 Creating background run...")
        run = await client.runs.create(
            thread_id=thread['thread_id'],
            assistant_id=assistant['assistant_id'],
            input={"messages": [{"role": "user", "content": "What is recursion?"}]}
        )
        
        print(f"✅ Background run created: {run['run_id']}")
        print(f"📊 Initial status: {run['status']}")
        
        # Step 2: Join the stream to watch execution
        print("\n🔗 Joining run stream...")
        
        counters = {"messages": 0, "values": 0, "metadata": 0, "end": 0}
        tokens_text = ""
        
        async for chunk in client.runs.join_stream(
            thread_id=thread['thread_id'],
            run_id=run['run_id'],
            stream_mode=["messages", "values"]
        ):
            counters[chunk.event] = counters.get(chunk.event, 0) + 1
            
            if chunk.event == "messages":
                msg_chunk, _ = chunk.data
                if hasattr(msg_chunk, 'content') and msg_chunk.content:
                    print(msg_chunk.content, end="", flush=True)
                    tokens_text += msg_chunk.content
            elif chunk.event == "values":
                print(f"\n📦 Values snapshot received")
            elif chunk.event == "end":
                print(f"\n🏁 Stream ended")
                break
                
            # Safety limit
            if counters.get("messages", 0) >= 50:
                break
        
        print(f"\n✅ Stream complete!")
        print(f"📊 Event counts: {counters}")
        print(f"📝 Tokens received: {len(tokens_text)} characters")
        
        # Step 3: Check final run status
        final_run = await client.runs.get(thread['thread_id'], run['run_id'])
        print(f"🏁 Final run status: {final_run['status']}")
        
        return counters.get("messages", 0) > 0
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run background + join test only"""
    
    print("🧪 Background Run + Join Stream Test")
    print("=" * 50)
    
    success = await test_background_run_then_join()
    
    print(f"\n{'=' * 50}")
    if success:
        print("✅ Background + Join pattern works correctly!")
    else:
        print("❌ Background + Join pattern has issues")
        print("💡 Check if background execution generates streaming events")
    
    return success

if __name__ == "__main__":
    asyncio.run(main()) 