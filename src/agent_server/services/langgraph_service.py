"""LangGraph integration service with official patterns"""
import json
import importlib.util
from typing import Dict, Any, Optional
from pathlib import Path


class LangGraphService:
    """Service to work with LangGraph CLI configuration and graphs"""
    
    def __init__(self, config_path: str = "langgraph.json"):
        self.config_path = Path(config_path)
        self.config: Optional[Dict[str, Any]] = None
        self._graph_registry: Dict[str, Any] = {}
        self._graph_cache: Dict[str, Any] = {}
        
    async def initialize(self):
        """Load langgraph.json configuration and setup graph registry"""
        if not self.config_path.exists():
            raise ValueError(f"LangGraph config not found: {self.config_path}")
        
        with open(self.config_path) as f:
            self.config = json.load(f)
        
        # Load graph registry from config
        self._load_graph_registry()
    
    def _load_graph_registry(self):
        """Load graph definitions from langgraph.json"""
        graphs_config = self.config.get("graphs", {})
        
        for graph_id, graph_path in graphs_config.items():
            # Parse path format: "./graphs/weather_agent.py:graph"
            if ":" not in graph_path:
                raise ValueError(f"Invalid graph path format: {graph_path}")
            
            file_path, export_name = graph_path.split(":", 1)
            self._graph_registry[graph_id] = {
                "file_path": file_path,
                "export_name": export_name
            }
    
    async def get_graph(self, graph_id: str, force_reload: bool = False):
        """Get a compiled graph by ID with caching and LangGraph integration"""
        if graph_id not in self._graph_registry:
            raise ValueError(f"Graph not found: {graph_id}")
        
        # Return cached graph if available and not forcing reload
        if not force_reload and graph_id in self._graph_cache:
            return self._graph_cache[graph_id]
        
        graph_info = self._graph_registry[graph_id]
        
        # Load graph from file
        base_graph = await self._load_graph_from_file(graph_id, graph_info)
        
        # Always ensure graphs are compiled with our Postgres checkpointer for persistence
        from ..core.database import db_manager
        
        if hasattr(base_graph, 'compile'):
            # Base graph is not compiled yet - compile with basic execution (no persistence for now)
            print(f"🔧 Compiling graph '{graph_id}' without persistence for testing")
            compiled_graph = base_graph.compile()
        else:
            # Graph is already compiled - use as-is for now
            print(f"🔧 Using pre-compiled graph '{graph_id}' as-is")
            compiled_graph = base_graph
        
        # Cache the compiled graph
        self._graph_cache[graph_id] = compiled_graph
        
        return compiled_graph
    
    async def _load_graph_from_file(self, graph_id: str, graph_info: Dict[str, str]):
        """Load graph from filesystem"""
        file_path = Path(graph_info["file_path"])
        if not file_path.exists():
            raise ValueError(f"Graph file not found: {file_path}")
        
        # Dynamic import of graph module
        spec = importlib.util.spec_from_file_location(
            f"graphs.{graph_id}",
            str(file_path.resolve())
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # Get the exported graph
        export_name = graph_info["export_name"]
        if not hasattr(module, export_name):
            raise ValueError(f"Graph export not found: {export_name} in {file_path}")
        
        graph = getattr(module, export_name)
        
        # The graph should already be compiled in the module
        # If it needs our checkpointer/store, we'll handle that during execution
        return graph
    
    def list_graphs(self) -> Dict[str, str]:
        """List all available graphs"""
        return {
            graph_id: info["file_path"] 
            for graph_id, info in self._graph_registry.items()
        }
    
    def invalidate_cache(self, graph_id: str = None):
        """Invalidate graph cache for hot-reload"""
        if graph_id:
            self._graph_cache.pop(graph_id, None)
        else:
            self._graph_cache.clear()
    
    def get_config(self) -> Optional[Dict[str, Any]]:
        """Get full langgraph.json configuration"""
        return self.config
    
    def get_dependencies(self) -> list:
        """Get dependencies from langgraph.json"""
        return self.config.get("dependencies", [])


# Global service instance
_langgraph_service = None


def get_langgraph_service() -> LangGraphService:
    """Get global LangGraph service instance"""
    global _langgraph_service
    if _langgraph_service is None:
        _langgraph_service = LangGraphService()
    return _langgraph_service


def inject_user_context(user, base_config: Dict = None) -> Dict:
    """Inject user context into LangGraph configuration for user isolation"""
    config = (base_config or {}).copy()
    config["configurable"] = config.get("configurable", {})
    
    # Simple user-based data scoping
    config["configurable"]["user_id"] = user.identity
    config["configurable"]["user_display_name"] = getattr(user, "display_name", user.identity)
    
    return config


def create_thread_config(thread_id: str, user, additional_config: Dict = None) -> Dict:
    """Create LangGraph configuration for a specific thread with user context"""
    base_config = {
        "configurable": {
            "thread_id": thread_id
        }
    }
    
    if additional_config:
        base_config.update(additional_config)
    
    return inject_user_context(user, base_config)


def create_run_config(run_id: str, thread_id: str, user, additional_config: Dict = None) -> Dict:
    """Create LangGraph configuration for a specific run with full context"""
    base_config = {
        "configurable": {
            "thread_id": thread_id,
            "run_id": run_id
        }
    }
    
    if additional_config:
        base_config.update(additional_config)
    
    return inject_user_context(user, base_config)