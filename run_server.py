#!/usr/bin/env python3
"""
Server startup script for testing.

This script:
1. Sets up the environment
2. Starts the FastAPI server
3. Can be used for testing our LangGraph integration
"""

import os
import uvicorn
from pathlib import Path

def setup_environment():
    """Set up environment variables for testing"""
    # Set database URL for development
    if not os.getenv("DATABASE_URL"):
        os.environ["DATABASE_URL"] = "postgresql+asyncpg://user:password@localhost:5432/langgraph_agent_server"
    
    # Set auth type (can be overridden)
    if not os.getenv("AUTH_TYPE"):
        os.environ["AUTH_TYPE"] = "noop"
    
    print(f"🔐 Auth Type: {os.getenv('AUTH_TYPE')}")
    print(f"🗄️  Database: {os.getenv('DATABASE_URL')}")

def main():
    """Start the server"""
    setup_environment()
    
    print("🚀 Starting LangGraph Agent Server...")
    print("📍 Server will be available at: http://localhost:8000")
    print("📊 API docs will be available at: http://localhost:8000/docs")
    print("🧪 Test with: python test_sdk_integration.py")
    
    uvicorn.run(
        "src.agent_server.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

if __name__ == "__main__":
    main()