#!/bin/bash

# Aegra Startup Script
# Starts PostgreSQL, Aegra backend, and Assistant-UI frontend

echo "🚀 Starting Aegra (Self-hosted LangGraph Alternative)..."
echo "==============================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Store PIDs globally
POSTGRES_PID=""
BACKEND_PID=""
FRONTEND_PID=""

# Function to cleanup on exit
cleanup() {
    echo -e "\n${YELLOW}Shutting down Aegra services...${NC}"
    
    # Kill frontend if running
    if [ ! -z "$FRONTEND_PID" ] && kill -0 $FRONTEND_PID 2>/dev/null; then
        echo -e "${YELLOW}Stopping frontend server...${NC}"
        kill $FRONTEND_PID 2>/dev/null
    fi
    
    # Kill backend if running
    if [ ! -z "$BACKEND_PID" ] && kill -0 $BACKEND_PID 2>/dev/null; then
        echo -e "${YELLOW}Stopping backend server...${NC}"
        kill $BACKEND_PID 2>/dev/null
    fi
    
    # Stop Docker containers
    echo -e "${YELLOW}Stopping PostgreSQL...${NC}"
    docker compose down postgres 2>/dev/null
    
    echo -e "${GREEN}✅ All Aegra services stopped${NC}"
    exit 0
}

# Set up trap to cleanup on script exit
trap cleanup EXIT INT TERM

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    echo -e "${RED}❌ Docker is not running. Please start Docker first.${NC}"
    exit 1
fi

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo -e "${RED}❌ uv is not installed. Installing now...${NC}"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="/Users/$USER/.local/bin:$PATH"
fi

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo -e "${BLUE}📁 Working directory: $SCRIPT_DIR${NC}"
echo ""

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}Creating Python virtual environment...${NC}"
    uv sync
fi

# Check if .env file exists
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    echo -e "${YELLOW}Creating .env file from .env.example...${NC}"
    cp .env.example .env
    echo -e "${YELLOW}⚠️  Please add your OPENAI_API_KEY to .env file if needed${NC}"
fi

# Start PostgreSQL database
echo -e "${GREEN}🗄️  Starting PostgreSQL database...${NC}"
docker compose up postgres -d

# Wait for PostgreSQL to be ready
echo -e "${YELLOW}Waiting for PostgreSQL to be ready...${NC}"
for i in {1..30}; do
    if docker exec aegra-agent-postgres-1 pg_isready -U user -d agent_protocol_server &> /dev/null; then
        echo -e "${GREEN}✅ PostgreSQL is ready!${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}❌ PostgreSQL failed to start${NC}"
        exit 1
    fi
    sleep 1
done

# Run database migrations
echo -e "${GREEN}🔄 Running database migrations...${NC}"
export PATH="/Users/$USER/.local/bin:$PATH"
source .venv/bin/activate
python3 scripts/migrate.py upgrade

# Start Aegra backend server
echo -e "${GREEN}🚀 Starting Aegra backend server...${NC}"
touch aegra-backend.log
python3 run_server.py &> aegra-backend.log &
BACKEND_PID=$!

# Wait for backend to be ready
echo -e "${YELLOW}Waiting for backend to start...${NC}"
for i in {1..30}; do
    if curl -s http://localhost:8000/health &> /dev/null; then
        echo -e "${GREEN}✅ Backend is ready!${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}❌ Backend failed to start. Check aegra-backend.log for errors.${NC}"
        exit 1
    fi
    sleep 1
done

# Check if frontend directory exists
FRONTEND_DIR="../assistant-ui-frontend-aegra"
if [ ! -d "$FRONTEND_DIR" ]; then
    echo -e "${RED}❌ Frontend directory not found: $FRONTEND_DIR${NC}"
    echo -e "${YELLOW}Please make sure the Aegra frontend is set up${NC}"
    exit 1
fi

# Setup and start frontend
echo -e "${GREEN}⚛️  Setting up Aegra frontend...${NC}"
cd "$FRONTEND_DIR"

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}Installing frontend dependencies...${NC}"
    npm install --legacy-peer-deps &> ../aegra-agent/aegra-frontend-install.log
    echo -e "${GREEN}✅ Frontend dependencies installed${NC}"
fi

# Check if .env.local exists with correct configuration
if [ ! -f ".env.local" ] || ! grep -q "8000" .env.local; then
    echo -e "${YELLOW}Creating Aegra frontend configuration...${NC}"
    cat > .env.local << EOF
# Aegra Backend Configuration
NEXT_PUBLIC_LANGGRAPH_API_URL=http://localhost:8000
NEXT_PUBLIC_LANGGRAPH_ASSISTANT_ID=agent

# Port configuration to avoid conflicts
PORT=3001
EOF
    echo -e "${GREEN}✅ Frontend configuration created${NC}"
fi

# Start frontend server
echo -e "${GREEN}🚀 Starting Aegra frontend...${NC}"
touch ../aegra-agent/aegra-frontend.log
npm run dev &> ../aegra-agent/aegra-frontend.log &
FRONTEND_PID=$!

# Wait for frontend to be ready
echo -e "${YELLOW}Waiting for frontend to start...${NC}"
for i in {1..30}; do
    if curl -s http://localhost:3001 &> /dev/null; then
        echo -e "${GREEN}✅ Frontend is ready!${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}❌ Frontend failed to start. Check aegra-frontend.log for errors.${NC}"
        exit 1
    fi
    sleep 1
done

echo ""
echo -e "${CYAN}${BOLD}===============================================${NC}"
echo -e "${CYAN}${BOLD}🎉 Aegra is running!${NC}"
echo -e "${CYAN}${BOLD}===============================================${NC}"
echo ""
echo -e "${BLUE}📍 Frontend (Chat UI):${NC} http://localhost:3001"
echo -e "${BLUE}📍 Backend API:${NC} http://localhost:8000"
echo -e "${BLUE}📍 API Documentation:${NC} http://localhost:8000/docs"
echo -e "${BLUE}📍 PostgreSQL:${NC} localhost:5432"
echo ""

# Open browser
echo -e "${YELLOW}Opening browser...${NC}"
sleep 2

# Detect OS and open browser accordingly
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    open http://localhost:3001
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux
    if command -v xdg-open &> /dev/null; then
        xdg-open http://localhost:3001
    fi
fi

echo -e "${GREEN}✅ Browser opened${NC}"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all Aegra services${NC}"
echo -e "${CYAN}Logs: aegra-backend.log, aegra-frontend.log${NC}"
echo ""

# Keep script running and monitor services
echo -e "${GREEN}Aegra services are running successfully!${NC}"
echo -e "${YELLOW}To view logs in real-time, open a new terminal and run:${NC}"
echo -e "${BLUE}  tail -f aegra-backend.log${NC}   (for backend logs)"
echo -e "${BLUE}  tail -f aegra-frontend.log${NC}  (for frontend logs)"
echo ""

while true; do
    # Check if processes are still running
    if ! kill -0 $BACKEND_PID 2>/dev/null; then
        echo -e "${RED}❌ Backend server has stopped unexpectedly${NC}"
        cleanup
        exit 1
    fi
    if ! kill -0 $FRONTEND_PID 2>/dev/null; then
        echo -e "${RED}❌ Frontend server has stopped unexpectedly${NC}"
        cleanup
        exit 1
    fi
    sleep 5
done