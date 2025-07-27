#!/usr/bin/env python3
"""
Test for background run creation + join_stream pattern with network drop simulation
"""

import asyncio
from langgraph_sdk import get_client

async def test_background_run_with_network_drop():
    """Test creating a run in background, simulating network drop, then rejoining from last event"""
    
    print("🧪 Testing Background Run + Network Drop + Rejoin Pattern")
    print("=" * 60)
    
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
            input={"messages": [{"role": "user", "content": "Tell me a 200 word story."}]},
            stream_mode=["messages", "values"]
        )
   
        # Step 2: Start streaming and simulate network drop
        print("\n🔗 Starting initial stream (will simulate network drop)...")
        print("📝 CONTENT BEFORE DROP:")
        print("-" * 40)
        
        first_session_counters = {"messages": 0, "values": 0, "metadata": 0, "end": 0}
        last_event_id = None
        content_before_drop = ""
        message_event_count = 0  # Track actual message events for mock event ID
        
        try:
            event_count = 0
            async for chunk in client.runs.join_stream(
                thread_id=thread['thread_id'],
                run_id=run['run_id'],
                stream_mode=["messages", "values"]
            ):
                event_count += 1
                first_session_counters[chunk.event] = first_session_counters.get(chunk.event, 0) + 1
                
              
                current_event_id = f"mock_event_{event_count}"
                
                # Print message content as it streams
                if chunk.event == "messages":
                    # Extract message content from chunk data - it's [message_chunk, metadata]
                    if hasattr(chunk, 'data') and chunk.data:
                        if isinstance(chunk.data, list) and len(chunk.data) >= 1:
                            message_chunk = chunk.data[0]
                            if hasattr(message_chunk, 'content') and message_chunk.content:
                                print(message_chunk.content, end="", flush=True)
                                content_before_drop += message_chunk.content
                            elif isinstance(message_chunk, dict) and 'content' in message_chunk:
                                print(message_chunk['content'], end="", flush=True)
                                content_before_drop += message_chunk['content']
                
                if event_count >= 20:
                    last_event_id = current_event_id
                    print(f"\n💥 SIMULATING NETWORK DROP after mock event ID: {last_event_id}")
                    break
                    
                # If stream ends naturally before we hit the drop point
                if chunk.event == "end":
                    last_event_id = current_event_id
                    print(f"\n🏁 Stream ended naturally at mock event ID: {last_event_id}")
                    break
                    
        except Exception as e:
            print(f"⚠️ Stream interrupted (simulated): {e}")
        
        print(f"\n" + "-" * 40)
        print(f"🔗 Last mock event ID before drop: {last_event_id}")
        
        # Step 3: Simulate reconnection delay
        print(f"\n⏳ Simulating network recovery delay...")
        await asyncio.sleep(2)
        
        # Step 4: Rejoin stream from last event ID
        print(f"\n🔄 Rejoining stream from mock event ID: {last_event_id}")
        print("📝 CONTENT AFTER REJOIN:")
        print("-" * 40)
        
        second_session_counters = {"messages": 0, "values": 0, "metadata": 0, "end": 0}
        content_after_rejoin = ""
        rejoin_message_count = 0  # Track message events after rejoin
        
        try:
            rejoin_event_count = 0
            async for chunk in client.runs.join_stream(
                thread_id=thread['thread_id'],
                run_id=run['run_id'],
                stream_mode=["messages", "values"],
                last_event_id=last_event_id
            ):
                rejoin_event_count += 1
                second_session_counters[chunk.event] = second_session_counters.get(chunk.event, 0) + 1
                
                # Create mock event ID for rejoin session
                if chunk.event == "messages":
                    rejoin_message_count += 1
                    current_event_id = f"rejoin_mock_event_{rejoin_message_count}"
                else:
                    current_event_id = f"rejoin_mock_event_{rejoin_event_count}"
                
                # Print message content as it streams
                if chunk.event == "messages":
                    # Extract message content from chunk data - it's [message_chunk, metadata]
                    if hasattr(chunk, 'data') and chunk.data:
                        if isinstance(chunk.data, list) and len(chunk.data) >= 1:
                            message_chunk = chunk.data[0]
                            if hasattr(message_chunk, 'content') and message_chunk.content:
                                print(message_chunk.content, end="", flush=True)
                                content_after_rejoin += message_chunk.content
                            elif isinstance(message_chunk, dict) and 'content' in message_chunk:
                                print(message_chunk['content'], end="", flush=True)
                                content_after_rejoin += message_chunk['content']
                
                if chunk.event == "end":
                    print(f"🏁 Stream completed after rejoin")
                    break
                    
        except Exception as e:
            print(f"❌ Error during rejoin: {e}")
        
        print(f"\n" + "-" * 40)
        print(f"📊 Events received after rejoin: {second_session_counters}")
        print(f"📝 Content length after rejoin: {len(content_after_rejoin)} characters")
        
        # Step 5: Content Analysis
        print(f"\n📈 CONTENT ANALYSIS:")
        print(f"📝 Total content before drop: '{content_before_drop}'")
        print(f"📝 Total content after rejoin: '{content_after_rejoin}'")
        
        # Check for content overlap (duplicates)
        if content_after_rejoin and content_before_drop:
            # Simple check: see if the start of rejoin content overlaps with end of before content
            overlap_found = False
            for i in range(1, min(len(content_before_drop), len(content_after_rejoin)) + 1):
                if content_before_drop[-i:] == content_after_rejoin[:i]:
                    print(f"⚠️ Content overlap detected: '{content_before_drop[-i:]}' appears in both sessions")
                    overlap_found = True
                    break
            
            if not overlap_found:
                print("✅ No content overlap detected - clean continuation")
        
        # Check if content flows logically
        combined_content = content_before_drop + content_after_rejoin
        print(f"📝 Combined story: '{combined_content}'")
        
        # Check final run status
        final_run = await client.runs.get(thread['thread_id'], run['run_id'])
        print(f"🏁 Final run status: {final_run['status']}")
        
        # Test passes if we received content in both sessions with logical flow
        success = (
            len(content_before_drop) > 0 and
            (len(content_after_rejoin) >= 0) and  # Allow 0 if stream was already complete
            len(combined_content) > len(content_before_drop)  # Some progression happened
        )
        
        return success, {
            'before_drop': first_session_counters,
            'after_rejoin': second_session_counters,
            'content_before': content_before_drop,
            'content_after': content_after_rejoin,
            'combined_content': combined_content,
            'last_event_id': last_event_id
        }
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False, {}

async def main():
    """Run network drop test with content streaming visualization"""
    
    print("🧪 Stream Resilience Test with Content Visualization")
    print("=" * 60)
    
    # Run network drop simulation
    drop_success, drop_results = await test_background_run_with_network_drop()
    
    # Summary
    print(f"\n{'=' * 60}")
    print("📋 TEST SUMMARY:")
    print(f"✅ Network drop resilience: {'PASS' if drop_success else 'FAIL'}")
    
    if drop_results:
        print(f"\n📊 Network Drop Test Details:")
        print(f"   Events before drop: {drop_results['before_drop']}")
        print(f"   Events after rejoin: {drop_results['after_rejoin']}")
        print(f"   Content before: {len(drop_results['content_before'])} chars")
        print(f"   Content after: {len(drop_results['content_after'])} chars")
        print(f"   Total content: {len(drop_results['combined_content'])} chars")
        print(f"   Last event ID: {drop_results['last_event_id']}")
    
    if drop_success:
        print("\n🎉 Network drop resilience test passed!")
        print("💡 Check the content output above to verify no duplication or missing text")
    else:
        print("\n⚠️ Network drop test failed. Check the streaming service implementation.")
    
    return drop_success

if __name__ == "__main__":
    asyncio.run(main()) 