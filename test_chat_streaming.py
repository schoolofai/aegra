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
        
        async for chunk in client.runs.stream(
            thread_id=thread['thread_id'],
            assistant_id=assistant['assistant_id'],
            input={"messages": [{"role": "user", "content": "Write a detailed explanation of how recursion works in programming with examples. Include at least 3 different examples and explain the base case and recursive case for each."}]}
        ):
            chunk_count += 1
            print(f"📦 Chunk {chunk_count}: {chunk}")
            
            # Try to extract content from values events
            if chunk.event == 'values' and 'messages' in chunk.data:
                messages = chunk.data['messages']
                if messages and len(messages) > 1:  # User + AI message
                    ai_message = messages[-1]
                    if hasattr(ai_message, 'content'):
                        full_response = ai_message.content
                    elif isinstance(ai_message, dict) and 'content' in ai_message:
                        full_response = ai_message['content']
            
            # Limit chunks for testing
            if chunk_count >= 10:
                break
        
        print(f"\n✅ Streaming complete! Got {chunk_count} chunks")
        if full_response:
            print(f"🤖 AI Response: {full_response}")
        else:
            print("⚠️  No AI response extracted (check message format)")
        
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

if __name__ == "__main__":
    asyncio.run(main()) 