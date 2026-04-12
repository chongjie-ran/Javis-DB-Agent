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


class FailingTool(BaseTool):
    """会失败的测试工具"""
    definition = ToolDefinition(
        name="failing_tool",
        description="总是抛出异常的工具",
        category="test",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="msg", type="string", description="错误消息", required=False, default="fail"),
        ],
    )

    async def execute(self, params: dict, context: dict) -> ToolResult:
        raise RuntimeError(params.get("msg", "intentional failure"))


class SlowTool(BaseTool):
    """执行很慢的工具"""
    definition = ToolDefinition(
        name="slow_tool",
        description="故意延迟的工具",
        category="test",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="delay", type="int", description="延迟秒数", required=False, default=5),
        ],
    )

    async def execute(self, params: dict, context: dict) -> ToolResult:
        import asyncio
        delay = params.get("delay", 5)
        await asyncio.sleep(delay)
        return ToolResult(success=True, data={"slept": delay})


class TestMCPAdvanced:
    """MCP高级测试 (MCP-004/005/009/010/011)"""

    def test_mcp_004_empty_tool_list(self):
        """MCP-004: 空工具注册时返回空列表"""
        server = MCPServer()
        result = server.list_tools()
        assert result.tools == []
        resp = server.handle_request("tools/list")
        assert resp["result"]["tools"] == []

    def test_mcp_005_duplicate_tool_name(self):
        """MCP-005: 重复工具名 - 覆盖行为"""
        server = MCPServer()

        class ToolV1(BaseTool):
            definition = ToolDefinition(name="same_name", description="版本1", category="test", risk_level=RiskLevel.L1_READ, params=[])

            async def execute(self, params: dict, context: dict) -> ToolResult:
                return ToolResult(success=True, data={"version": 1})

        class ToolV2(BaseTool):
            definition = ToolDefinition(name="same_name", description="版本2", category="test", risk_level=RiskLevel.L1_READ, params=[])

            async def execute(self, params: dict, context: dict) -> ToolResult:
                return ToolResult(success=True, data={"version": 2})

        server.register_tool(ToolV1())
        server.register_tool(ToolV2())  # 覆盖
        result = server.list_tools()
        assert len(result.tools) == 1
        # 后注册的覆盖前面的
        assert "[test] 版本2" in result.tools[0].description

    @pytest.mark.asyncio
    async def test_mcp_009_wrong_param_type(self):
        """MCP-009: 参数类型错误 - 服务器接受任意类型，静默传递"""
        server = MCPServer()
        server.register_tool(DummyTool())
        # DummyTool的id参数期望string，但传入int
        # 当前server行为：静默传递不验证，is_error仍为False
        resp = await server.call_tool("dummy_query", {"id": 12345, "limit": "not_a_number"})
        # 验证：错误情况下is_error仍为False（无验证机制）
        # 期望未来版本有类型验证
        assert resp.is_error is False
        # 返回结果包含原始参数
        assert "12345" in resp.content[0]["text"]

    @pytest.mark.asyncio
    async def test_mcp_010_tool_execution_timeout(self):
        """MCP-010: 工具执行超时"""
        server = MCPServer()
        server.register_tool(SlowTool())
        import asyncio
        try:
            # 设置极短超时来触发TimeoutError
            resp = await asyncio.wait_for(
                server.call_tool("slow_tool", {"delay": 10}),
                timeout=0.1
            )
            # 不应该到达这里
            assert False, "Should have timed out"
        except asyncio.TimeoutError:
            pass  # 预期行为

    @pytest.mark.asyncio
    async def test_mcp_011_tool_exception(self):
        """MCP-011: 工具抛出异常"""
        server = MCPServer()
        server.register_tool(FailingTool())
        resp = await server.call_tool("failing_tool", {"msg": "test error"})
        assert resp.is_error is True
        # 错误信息应包含异常内容
        content_text = resp.content[0]["text"] if isinstance(resp.content[0], dict) else str(resp.content[0])
        assert "test error" in content_text or "RuntimeError" in content_text
