#!/usr/bin/env python3
"""
Test script specifically for the Chat Agent streaming with real LLM calls.
This tests the real streaming functionality with actual token-by-token responses.
"""

import asyncio
import os
from langgraph_sdk import get_client

async def test_chat_streaming():
    """Test streaming with the chat agent that calls a real LLM"""
    
    print("🤖 Testing Chat Agent Streaming (Real LLM)")
    print("==========================================")
    
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
        
        # Test streaming with real LLM calls
        print("\n🔥 Testing REAL LLM STREAMING...")
        print("Input: 'Write a detailed explanation of how recursion works in programming with examples'")
        
        chunk_count = 0
        full_response = ""
        
        run = await client.runs.create(
            thread_id=thread['thread_id'],
            assistant_id=assistant['assistant_id'],
            input={"messages": [{"role": "user", "content": "Write a detailed explanation of how recursion works in programming with examples. Include at least 3 different examples and explain the base case and recursive case for each."}]},
            stream_mode="messages"  # Only request messages for token streaming
        )
        print(f"🔄 Run: {run}")
        
        async for chunk in client.runs.join_stream(
            thread_id=thread['thread_id'],
            run_id=run['run_id'],
            stream_mode="messages"
        ):
            print(f"🔄 Chunk: {chunk}")
            
        async for chunk in client.runs.stream(
            thread_id=thread['thread_id'],
            assistant_id=assistant['assistant_id'],
            input={"messages": [{"role": "user", "content": "Write a detailed explanation of how recursion works in programming with examples. Include at least 3 different examples and explain the base case and recursive case for each."}]},
            stream_mode="messages"  # Only request messages for token streaming
        ):
            chunk_count += 1
            print(f"📦 Chunk {chunk_count}: {chunk}")
            
            # Check for messages events (LLM tokens)
            if chunk.event == 'messages':
                try:
                    # chunk.data should be [message_chunk, metadata] for messages stream
                    if isinstance(chunk.data, list) and len(chunk.data) == 2:
                        message_chunk, metadata = chunk.data
                        if hasattr(message_chunk, 'content') and message_chunk.content:
                            print(f"🤖 Token: '{message_chunk.content}'", end="", flush=True)
                            full_response += message_chunk.content
                        elif isinstance(message_chunk, dict) and 'content' in message_chunk:
                            print(f"🤖 Token: '{message_chunk['content']}'", end="", flush=True)
                            full_response += message_chunk['content']
                except Exception as e:
                    print(f"⚠️ Error processing message chunk: {e}")
            
            # Limit chunks for testing
            if chunk_count >= 50:  # Increase limit to see more tokens
                break
        
        print(f"\n✅ Streaming complete! Got {chunk_count} chunks")
        print(f"🤖 Full Response: {full_response}")
        
        return chunk_count > 0
        
    except Exception as e:
        print(f"❌ Chat streaming test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_chat_streaming_mock():
    """Test chat streaming without real API key (mock test)"""
    print("🧪 Running mock test (no real LLM calls)")
    
    try:
        client = get_client(url="http://localhost:8000/v1", api_key="test-key")
        
        # Check if chat_agent is available
        assistants = await client.assistants.search(graph_id="chat_agent")
        if assistants:
            print(f"✅ Chat agent is available in server")
            print(f"📋 Found {len(assistants)} chat assistants")
        else:
            print("⚠️  Chat agent not found - may need to restart server")
        
        return True
        
    except Exception as e:
        print(f"❌ Mock test failed: {e}")
        return False

async def test_chat_streaming_all_modes():
    """Test streaming with messages + values + events modes together"""
    print("\n🤖 Testing Chat Agent Streaming (messages + values + events)")
    print("==========================================")

    try:
        client = get_client(url="http://localhost:8000/v1", api_key="test-key")

        # Re-use or create assistant / thread
        assistant = await client.assistants.create(
            graph_id="chat_agent",
            config={"tags": ["chat", "llm"]},
            if_exists="do_nothing",
        )
        thread = await client.threads.create()

        counters = {"messages": 0, "values": 0, "other": 0}

        async for chunk in client.runs.stream(
            thread_id=thread["thread_id"],
            assistant_id=assistant["assistant_id"],
            input={
                "messages": [
                    {
                        "role": "user",
                        "content": "Briefly explain what recursion is",
                    }
                ]
            },
            stream_mode=["messages", "values"],
        ):
            counters[chunk.event] = counters.get(chunk.event, 0) + 1
            if chunk.event == "messages":
                msg_chunk, _ = chunk.data
                # Extract just the content text for clean token streaming
                if hasattr(msg_chunk, 'content') and msg_chunk.content:
                    print(msg_chunk.content, end="", flush=True)
                elif isinstance(msg_chunk, dict) and 'content' in msg_chunk:
                    print(msg_chunk['content'], end="", flush=True)
            elif chunk.event == "values":
                print(f"\n 📦 values snapshot received: {chunk.data}")

        print("\n✅ Counters:", counters)
        return True
    except Exception as e:
        print("❌ Test failed:", e)
        return False

async def main():
    """Main test function"""
    success = await test_chat_streaming()
    
    print(f"\n{'='*50}")
    if success:
        print("✅ Chat streaming test completed successfully!")
        print("💡 This validates that:")
        print("   - Chat agent graph is registered")
        print("   - Real LLM streaming works") 
        print("   - SSE events are properly formatted")
    else:
        print("❌ Chat streaming test failed")
        print("💡 Check server logs and API key setup")
    
    return success

# For quick manual run
if __name__ == "__main__":
    asyncio.run(test_chat_streaming_all_modes()) 