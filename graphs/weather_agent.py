"""Weather Agent Graph - Simple example agent for weather queries"""
from typing import Annotated, Literal, TypedDict, List
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, add_messages, END


class WeatherState(TypedDict):
    """State for the Weather Agent"""
    messages: Annotated[List[BaseMessage], add_messages]
    location: str = ""
    temperature: float = 0.0


def extract_location(state: WeatherState) -> WeatherState:
    """Extract location from the user's message"""
    messages = state["messages"]
    if not messages:
        return {"location": "unknown"}
    
    last_message = messages[-1].content if hasattr(messages[-1], 'content') else str(messages[-1])
    
    # Simple location extraction (in production, use NER or LLM)
    location = "San Francisco"  # Default for demo
    if "new york" in last_message.lower() or "nyc" in last_message.lower():
        location = "New York"
    elif "london" in last_message.lower():
        location = "London"
    elif "tokyo" in last_message.lower():
        location = "Tokyo"
    
    return {"location": location}


def get_weather(state: WeatherState) -> WeatherState:
    """Simulate getting weather data for the location"""
    location = state.get("location", "unknown")
    
    # Mock weather data (in production, call actual weather API)
    weather_data = {
        "San Francisco": 68.0,
        "New York": 45.0,
        "London": 52.0,
        "Tokyo": 61.0,
        "unknown": 70.0
    }
    
    temperature = weather_data.get(location, 70.0)
    return {"temperature": temperature}


def generate_response(state: WeatherState) -> WeatherState:
    """Generate weather response message"""
    location = state.get("location", "unknown location")
    temperature = state.get("temperature", 0.0)
    
    response_text = f"The current temperature in {location} is {temperature}°F."
    
    response_message = AIMessage(content=response_text)
    
    return {"messages": [response_message]}


# Create the weather agent graph
workflow = StateGraph(WeatherState)

# Add nodes
workflow.add_node("extract_location", extract_location)
workflow.add_node("get_weather", get_weather)
workflow.add_node("generate_response", generate_response)

# Define the flow
workflow.set_entry_point("extract_location")
workflow.add_edge("extract_location", "get_weather")
workflow.add_edge("get_weather", "generate_response")
workflow.add_edge("generate_response", END)

# Compile the graph for export
graph = workflow.compile()