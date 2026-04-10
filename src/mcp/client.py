"""MCP Client - 调用外部MCP Server (V3.2 P1)

MCP Client核心职责：
1. 连接外部MCP Server（通过HTTP/stdio）
2. 调用外部工具（tools/list, tools/call）
3. 统一结果格式

使用场景:
- 调用Slack/Jira等外部MCP Server
- 多Agent协作（A2A协议）
"""
import logging
from typing import Optional, Any
import httpx

from .protocol import (
    MCPTool,
    MCPListToolsResult,
    MCPToolCallResult,
    MCP_PROTOCOL_VERSION,
)

logger = logging.getLogger(__name__)


class MCPClient:
    """
    MCP Client实现
    
    支持两种连接方式:
    1. HTTP Server: 通过HTTP POST调用
    2. Local: 直接实例化调用（用于同进程MCP Server）
    """

    def __init__(self, server_url: Optional[str] = None, timeout: int = 30):
        """
        Args:
            server_url: MCP Server HTTP地址，如 "http://localhost:8080/mcp"
            timeout: 请求超时秒数
        """
        self._server_url = server_url
        self._timeout = timeout
        self._tools: list[MCPTool] = []
        self._local_server: Optional["MCPServer"] = None

    def connect_local(self, server: "MCPServer") -> None:
        """连接到本地MCP Server（同进程）"""
        self._local_server = server
        self._server_url = None
        # 同步工具列表
        result = server.list_tools()
        self._tools = result.tools

    async def list_tools(self) -> MCPListToolsResult:
        """
        获取远程Server的工具列表
        
        Returns:
            MCPListToolsResult
        """
        if self._local_server:
            result = self._local_server.list_tools()
            self._tools = result.tools
            return result
        
        if not self._server_url:
            raise ValueError("No server URL configured")
        
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                self._server_url,
                json={"jsonrpc": "2.0", "method": "tools/list", "id": "1"},
            )
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                raise RuntimeError(f"MCP error: {data['error']}")
            
            result_data = data.get("result", {})
            tools = [
                MCPTool(
                    name=t["name"],
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {}),
                )
                for t in result_data.get("tools", [])
            ]
            self._tools = tools
            return MCPListToolsResult(tools=tools)

    async def call_tool(self, name: str, arguments: dict) -> MCPToolCallResult:
        """
        调用远程工具
        
        Args:
            name: 工具名称
            arguments: 工具参数
        
        Returns:
            MCPToolCallResult
        """
        if self._local_server:
            return await self._local_server.call_tool(name, arguments)
        
        if not self._server_url:
            raise ValueError("No server URL configured")
        
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
                "id": "1",
            }
            response = await client.post(self._server_url, json=payload)
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                raise RuntimeError(f"MCP error: {data['error']}")
            
            result_data = data.get("result", {})
            return MCPToolCallResult(
                content=result_data.get("content", []),
                is_error=result_data.get("isError", False),
            )

    def get_local_tools(self) -> list[MCPTool]:
        """获取已缓存的工具列表"""
        return list(self._tools)

    def get_tool(self, name: str) -> Optional[MCPTool]:
        """根据名称获取工具定义"""
        for t in self._tools:
            if t.name == name:
                return t
        return None


# 全局单例（默认客户端）
_mcp_client: Optional[MCPClient] = None


def get_mcp_client(server_url: Optional[str] = None) -> MCPClient:
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPClient(server_url=server_url)
    return _mcp_client
