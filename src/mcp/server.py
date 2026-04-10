"""MCP Server - 暴露工具为MCP协议 (V3.2 P1)

MCP Server核心职责：
1. 接收 tools/list 请求，返回所有工具的MCP JSON Schema
2. 接收 tools/call 请求，执行对应工具并返回结果
3. 工具注册时自动生成MCP Schema

暴露的工具类别: query/analysis/backup/performance/action
"""
import logging
from typing import Optional

from .protocol import (
    MCPTool,
    MCPListToolsResult,
    MCPToolCallResult,
    MCPToolCallRequest,
    MCP_PROTOCOL_VERSION,
)

logger = logging.getLogger(__name__)


class MCPServer:
    """
    MCP Server实现
    
    使用示例:
        server = MCPServer()
        server.register_tool(query_tool)
        result = server.list_tools()  # MCP tools/list
        result = server.call_tool("query_instance_status", {"instance_id": "INS-001"})  # MCP tools/call
    """

    def __init__(self):
        self._tools: dict[str, MCPTool] = {}
        self._tool_instances: dict[str, "BaseTool"] = {}  # name -> BaseTool instance
        self._version = MCP_PROTOCOL_VERSION

    def register_tool(self, tool_instance: "BaseTool") -> None:
        """注册工具，自动生成MCP Schema"""
        from src.tools.base import BaseTool
        assert isinstance(tool_instance, BaseTool), f"必须继承BaseTool: {type(tool_instance)}"
        
        name = tool_instance.name
        defn = tool_instance.definition_dict
        
        mcp_tool = MCPTool.from_tool_definition(
            name=name,
            description=defn.get("description", ""),
            params=defn.get("params", []),
            category=defn.get("category", ""),
        )
        
        self._tools[name] = mcp_tool
        self._tool_instances[name] = tool_instance
        logger.info(f"[MCPServer] Registered tool: {name}")

    def unregister_tool(self, name: str) -> bool:
        """注销工具"""
        self._tools.pop(name, None)
        self._tool_instances.pop(name, None)
        return True

    def list_tools(self) -> MCPListToolsResult:
        """
        MCP tools/list - 列出所有可用工具
        
        Returns:
            MCPListToolsResult with all registered tools
        """
        tools = list(self._tools.values())
        logger.debug(f"[MCPServer] list_tools: {len(tools)} tools")
        return MCPListToolsResult(tools=tools)

    async def call_tool(self, name: str, arguments: dict, 
                       context: Optional[dict] = None) -> MCPToolCallResult:
        """
        MCP tools/call - 调用指定工具
        
        Args:
            name: 工具名称
            arguments: 工具参数
            context: 执行上下文(session_id, user_id等)
        
        Returns:
            MCPToolCallResult
        """
        if name not in self._tool_instances:
            return MCPToolCallResult(
                content=[{"type": "text", "text": f"Tool not found: {name}"}],
                is_error=True,
            )
        
        tool = self._tool_instances[name]
        ctx = context or {}
        
        try:
            result = await tool.execute(arguments, ctx)
            return MCPToolCallResult.from_tool_result(
                success=result.success,
                data=result.data,
                error=result.error,
            )
        except Exception as e:
            logger.error(f"[MCPServer] Tool {name} failed: {e}")
            return MCPToolCallResult(
                content=[{"type": "text", "text": f"Execution error: {type(e).__name__}: {e}"}],
                is_error=True,
            )

    def handle_request(self, method: str, params: Optional[dict] = None) -> dict:
        """
        处理MCP JSON-RPC请求
        
        Args:
            method: "tools/list" or "tools/call"
            params: 请求参数
        
        Returns:
            MCP JSON-RPC响应
        """
        import uuid
        
        try:
            if method == "tools/list":
                result = self.list_tools()
                return {
                    "jsonrpc": "2.0",
                    "id": str(uuid.uuid4()),
                    "result": result.to_mcp_dict(),
                }
            elif method == "tools/call":
                req = MCPToolCallRequest.from_dict(params or {})
                import asyncio
                result = asyncio.run(self.call_tool(req.name, req.arguments))
                return {
                    "jsonrpc": "2.0",
                    "id": str(uuid.uuid4()),
                    "result": result.to_mcp_dict(),
                }
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": str(uuid.uuid4()),
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
        except Exception as e:
            logger.error(f"[MCPServer] Request {method} failed: {e}")
            return {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "error": {"code": -32603, "message": str(e)},
            }

    def get_tool_schemas(self) -> list[dict]:
        """获取所有工具的MCP Schema（用于注册到外部MCP Client）"""
        return [t.to_mcp_dict() for t in self._tools.values()]

    def sync_from_registry(self, registry: "ToolRegistry") -> int:
        """从ToolRegistry同步所有工具"""
        tools = registry.list_tools(enabled_only=True)
        from src.tools.base import BaseTool
        count = 0
        for defn in tools:
            tool = registry.get_tool(defn["name"])
            if tool and isinstance(tool, BaseTool):
                self.register_tool(tool)
                count += 1
        logger.info(f"[MCPServer] Synced {count} tools from registry")
        return count


# 全局单例
_mcp_server: Optional[MCPServer] = None


def get_mcp_server() -> MCPServer:
    global _mcp_server
    if _mcp_server is None:
        _mcp_server = MCPServer()
    return _mcp_server
