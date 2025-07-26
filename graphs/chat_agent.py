#!/usr/bin/env python3
"""
Simple Chat Agent that calls an actual LLM and streams responses.
This is the real test for our streaming implementation.

State: Just messages (list of messages)
"""

from typing import TypedDict, List, Any
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
import os


class ChatState(TypedDict):
    """Simple state with just messages"""
    messages: List[BaseMessage]


def call_llm(state: ChatState) -> ChatState:
    """Call the LLM with the current messages"""
    
    # Initialize OpenAI LLM
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.7,
        api_key=os.getenv("OPENAI_API_KEY"),
    )
    
    # Get the messages from state
    messages = state["messages"]
    
    # Call the LLM
    response = llm.invoke(messages)
    
    # Add the response to messages
    updated_messages = messages + [response]
    
    return {"messages": updated_messages}


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


if __name__ == "__main__":
    # Test the graph locally
    import asyncio
    
    async def test_chat():
        initial_state = {
            "messages": [HumanMessage(content="Hello! How are you today?")]
        }
        
        print("🤖 Testing chat graph...")
        result = await chat_graph.ainvoke(initial_state)
        print(f"📝 Result: {result['messages'][-1].content}")
    
    asyncio.run(test_chat()) 