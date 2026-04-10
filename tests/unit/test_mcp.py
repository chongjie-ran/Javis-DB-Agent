"""MCP协议单元测试 (V3.2 P1)"""
import pytest
import sys
sys.path.insert(0, "/Users/chongjieran/.openclaw/workspace/Javis-DB-Agent")

from src.mcp.protocol import (
    MCPTool, MCPListToolsResult, MCPToolCallResult,
    MCPToolCallRequest, MCP_PROTOCOL_VERSION, ToolSchemaType,
)
from src.mcp.server import MCPServer, get_mcp_server
from src.mcp.client import MCPClient
from src.tools.base import ToolParam, ToolDefinition, ToolResult, RiskLevel, BaseTool


class DummyTool(BaseTool):
    """测试用虚拟工具"""
    definition = ToolDefinition(
        name="dummy_query",
        description="虚拟查询工具",
        category="query",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="id", type="string", description="ID", required=True),
            ToolParam(name="limit", type="int", description="限制", required=False, default=10),
        ],
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        return ToolResult(success=True, data={"id": params.get("id"), "limit": params.get("limit", 10)})


class TestMCPTool:
    """MCPTool格式测试"""

    def test_protocol_version(self):
        assert MCP_PROTOCOL_VERSION == "2024-11-05"

    def test_tool_from_definition(self):
        params = [
            ToolParam(name="id", type="string", description="ID", required=True),
            ToolParam(name="count", type="int", description="数量", required=False, default=5),
        ]
        tool = MCPTool.from_tool_definition("test", "测试", params, "query")
        schema = tool.to_mcp_dict()
        assert schema["name"] == "test"
        assert "[query]" in schema["description"]
        assert schema["inputSchema"]["type"] == "object"
        assert "id" in schema["inputSchema"]["required"]
        assert schema["inputSchema"]["properties"]["id"]["type"] == "string"
        assert schema["inputSchema"]["properties"]["count"]["type"] == "integer"
        assert schema["inputSchema"]["properties"]["count"]["default"] == 5


class TestMCPServer:
    """MCPServer功能测试"""

    def test_server_singleton(self):
        s1 = get_mcp_server()
        s2 = get_mcp_server()
        assert s1 is s2

    def test_register_and_list(self):
        server = MCPServer()
        dummy = DummyTool()
        server.register_tool(dummy)
        result = server.list_tools()
        assert len(result.tools) == 1
        assert result.tools[0].name == "dummy_query"

    def test_list_tools_jsonrpc(self):
        server = MCPServer()
        server.register_tool(DummyTool())
        resp = server.handle_request("tools/list")
        assert resp["jsonrpc"] == "2.0"
        assert "result" in resp
        assert len(resp["result"]["tools"]) == 1

    def test_call_unknown_tool(self):
        server = MCPServer()
        resp = server.handle_request("tools/call", {"name": "non_existent", "arguments": {}})
        assert resp["result"]["isError"] is True

    def test_unknown_method(self):
        server = MCPServer()
        resp = server.handle_request("tools/unknown")
        assert "error" in resp
        assert resp["error"]["code"] == -32601


class TestMCPClient:
    """MCPClient功能测试"""

    def test_client_init(self):
        client = MCPClient(server_url="http://localhost:8080/mcp")
        assert client._server_url == "http://localhost:8080/mcp"
        assert client._timeout == 30

    def test_client_local_connect(self):
        server = MCPServer()
        server.register_tool(DummyTool())
        client = MCPClient()
        client.connect_local(server)
        assert client._local_server is server
        assert len(client._tools) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
