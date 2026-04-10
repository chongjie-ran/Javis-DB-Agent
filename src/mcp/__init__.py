"""MCP (Model Context Protocol) 支持 (V3.2 P1)"""
from .server import MCPServer, get_mcp_server
from .client import MCPClient, get_mcp_client
from .protocol import MCPTool, MCPListToolsResult, MCPToolCallResult, MCP_PROTOCOL_VERSION

__all__ = [
    "MCPServer",
    "get_mcp_server",
    "MCPClient", 
    "get_mcp_client",
    "MCPTool",
    "MCPListToolsResult",
    "MCPToolCallResult",
    "MCP_PROTOCOL_VERSION",
]
