#!/usr/bin/env python3
"""
Simple Chat Agent using shared demo logic.
Maintains Aegra scaffolding for proper integration.

State: Just messages (list of messages)
"""

from typing import TypedDict, List, Any
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END

# Import shared logic
import sys
sys.path.append('/Users/niladribose/code/ScottishAILessons/agents')
from shared_chat_logic import chat_node


class ChatState(TypedDict):
    """Simple state with just messages"""
    messages: List[BaseMessage]


from langchain_core.runnables import RunnableConfig


async def call_llm(state: ChatState, config: RunnableConfig | None = None) -> ChatState:
    """Call shared demo logic instead of LLM.

    For debugging we log / print any custom keys that reached us via
    ``config`` to prove the server's pass-through behaviour.
    """
    
    # Use shared chat_node
    result = await chat_node(state)
    
    # Convert AIMessage to AIMessageChunk for Aegra streaming compatibility
    messages = result.get("messages", [])
    if messages and len(messages) > 0:
        from langchain_core.messages import AIMessageChunk
        last_msg = messages[-1]
        
        # Check if the last message is an AI message that needs conversion
        if hasattr(last_msg, 'type') and last_msg.type == 'ai':
            # Create an AIMessageChunk with proper format
            chunk = AIMessageChunk(
                content=last_msg.content,
                # Add run-- prefix to match expected format
                id=f"run--{last_msg.id}" if hasattr(last_msg, 'id') and last_msg.id else f"run--{id(last_msg)}"
            )
            # Return messages with the converted chunk
            return {"messages": messages[:-1] + [chunk]}
    
    return result


def create_chat_graph():
    """Create a simple chat graph"""
    
    # Create the graph
    workflow = StateGraph(ChatState)
    
    # Add the LLM node
    workflow.add_node("llm", call_llm)
    
    # Set entry point
    workflow.set_entry_point("llm")
    
    # Add edge to end
    workflow.add_edge("llm", END)
    
    # Compile the graph
    return workflow.compile()


# Create the graph instance
chat_graph = create_chat_graph()

# Export as 'graph' for Aegra configuration
graph = chat_graph


if __name__ == "__main__":
    # Test the graph locally
    import asyncio
    import dotenv
    dotenv.load_dotenv()
    async def test_chat():
        initial_state = {
            "messages": [HumanMessage(content="Hello! How are you today?")]
        }
        
        print("🤖 Testing chat graph...")
        async for event in chat_graph.astream(initial_state, stream_mode=["messages", "values"]):
            print(event)
            print("\n\n")
    
    asyncio.run(test_chat()) 