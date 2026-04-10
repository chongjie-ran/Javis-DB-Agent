"""MCP 协议类型定义 (V3.2 P1)

参考: https://modelcontextprotocol.io
MCP协议核心:
- tools/list: 列出所有可用工具
- tools/call: 调用指定工具
"""
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum

MCP_PROTOCOL_VERSION = "2024-11-05"


class ToolSchemaType(str, Enum):
    """MCP工具输入类型"""
    OBJECT = "object"
    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    ARRAY = "array"


@dataclass
class MCPToolInputProperty:
    """MCP工具参数定义"""
    type: str = "string"
    description: str = ""
    default: Any = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    enum: Optional[list] = None

    def to_mcp_dict(self) -> dict:
        result = {"type": self.type, "description": self.description}
        if self.default is not None:
            result["default"] = self.default
        if self.minimum is not None:
            result["minimum"] = self.minimum
        if self.maximum is not None:
            result["maximum"] = self.maximum
        if self.enum is not None:
            result["enum"] = self.enum
        return result


@dataclass
class MCPTool:
    """
    MCP工具定义 (MCP Protocol 规范)

    MCP JSON Schema格式:
    {
        "name": "tool_name",
        "description": "...",
        "inputSchema": {
            "type": "object",
            "properties": {...},
            "required": [...]
        }
    }
    """
    name: str
    description: str = ""
    input_schema: dict = field(default_factory=dict)

    def to_mcp_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }

    @classmethod
    def from_tool_definition(cls, name: str, description: str,
                               params: list, category: str = "") -> "MCPTool":
        """从Javis ToolDefinition转换为MCP格式
        params可以是ToolParam对象列表，也可以是已序列化的dict列表
        """
        properties = {}
        required = []

        for p in params:
            # 统一为dict访问
            p_dict = p if isinstance(p, dict) else {
                "name": p.name, "type": p.type, "description": p.description,
                "required": p.required, "default": p.default, "constraints": p.constraints,
            }

            prop = MCPToolInputProperty(
                type=str(p_dict.get("type", "string")),
                description=str(p_dict.get("description", "")),
                default=p_dict.get("default"),
            )
            # 映射Python类型 -> JSON Schema类型
            type_map = {"string": "string", "int": "integer", "float": "number",
                       "bool": "boolean", "array": "array", "object": "object"}
            prop.type = type_map.get(prop.type, "string")

            # 处理约束
            constraints = p_dict.get("constraints") or {}
            if "min" in constraints:
                prop.minimum = float(constraints["min"])
            if "max" in constraints:
                prop.maximum = float(constraints["max"])
            if "enum" in constraints:
                prop.enum = constraints["enum"]

            p_name = str(p_dict.get("name", ""))
            properties[p_name] = prop.to_mcp_dict()
            if p_dict.get("required"):
                required.append(p_name)

        input_schema = {"type": "object", "properties": properties}
        if required:
            input_schema["required"] = required

        return cls(
            name=name,
            description=f"[{category}] {description}" if category else description,
            input_schema=input_schema,
        )


@dataclass
class MCPListToolsResult:
    """tools/list 响应"""
    tools: list[MCPTool]
    protocols_version: str = MCP_PROTOCOL_VERSION

    def to_mcp_dict(self) -> dict:
        return {
            "tools": [t.to_mcp_dict() for t in self.tools],
            "protocolVersion": self.protocols_version,
        }


@dataclass
class MCPToolCallResult:
    """tools/call 响应"""
    content: list[dict]
    is_error: bool = False

    def to_mcp_dict(self) -> dict:
        return {
            "content": self.content,
            "isError": self.is_error,
        }

    @classmethod
    def from_tool_result(cls, success: bool, data: Any = None,
                         error: Optional[str] = None) -> "MCPToolCallResult":
        if success and data is not None:
            content = [{"type": "text", "text": str(data)}]
            return cls(content=content, is_error=False)
        elif not success:
            content = [{"type": "text", "text": str(error or "Unknown error")}]
            return cls(content=content, is_error=True)
        else:
            content = [{"type": "text", "text": "OK"}]
            return cls(content=content, is_error=False)


@dataclass
class MCPToolCallRequest:
    """tools/call 请求"""
    name: str
    arguments: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "MCPToolCallRequest":
        return cls(
            name=data.get("name", ""),
            arguments=data.get("arguments", {}),
        )
