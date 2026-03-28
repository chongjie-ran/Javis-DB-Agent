"""工具基类定义"""
from abc import ABC, abstractmethod
from enum import IntEnum
from typing import Any, Optional
from pydantic import BaseModel, Field


class RiskLevel(IntEnum):
    """风险级别"""
    L1_READ = 1      # 只读分析（无需审批）
    L2_DIAGNOSE = 2  # 自动诊断（无需审批）
    L3_LOW_RISK = 3 # 低风险执行（日志记录）
    L4_MEDIUM = 4    # 中风险执行（单签审批）
    L5_HIGH = 5      # 高风险/禁止（双人审批）


class ToolParam(BaseModel):
    """工具参数定义"""
    name: str = Field(..., description="参数名称")
    type: str = Field(..., description="参数类型: string/int/float/bool/array/object")
    description: str = Field("", description="参数描述")
    required: bool = Field(True, description="是否必填")
    default: Any = Field(None, description="默认值")
    constraints: dict[str, Any] = Field(default_factory=dict, description="参数约束")


class ToolDefinition(BaseModel):
    """工具定义"""
    name: str = Field(..., description="工具名称")
    description: str = Field("", description="工具描述")
    category: str = Field(..., description="工具类别: query/analysis/action")
    risk_level: RiskLevel = Field(RiskLevel.L1_READ, description="风险级别")
    params: list[ToolParam] = Field(default_factory=list, description="参数列表")
    auth_required: list[str] = Field(default_factory=list, description="所需权限")
    pre_check: str = Field("", description="执行前检查描述")
    post_check: str = Field("", description="执行后检查描述")
    example: str = Field("", description="使用示例")


class ToolResult(BaseModel):
    """工具执行结果"""
    success: bool
    data: Any = None
    error: Optional[str] = None
    tool_name: str = ""
    execution_time_ms: int = 0


class BaseTool(ABC):
    """工具基类"""
    
    definition: ToolDefinition
    
    def __init__(self):
        self._definition = self.definition
    
    @property
    def name(self) -> str:
        return self._definition.name
    
    @property
    def definition_dict(self) -> dict:
        return self._definition.model_dump()
    
    def validate_params(self, params: dict) -> tuple[bool, Optional[str]]:
        """参数校验"""
        for p in self._definition.params:
            if p.required and p.name not in params:
                return False, f"缺少必填参数: {p.name}"
            if p.name in params:
                value = params[p.name]
                # 类型检查
                expected_type = p.type
                if expected_type == "int" and not isinstance(value, int):
                    try:
                        params[p.name] = int(value)
                    except (ValueError, TypeError):
                        return False, f"参数 {p.name} 应为整数"
                elif expected_type == "float" and not isinstance(value, (int, float)):
                    try:
                        params[p.name] = float(value)
                    except (ValueError, TypeError):
                        return False, f"参数 {p.name} 应为数字"
                elif expected_type == "string" and not isinstance(value, str):
                    params[p.name] = str(value)
                elif expected_type == "bool" and not isinstance(value, bool):
                    params[p.name] = bool(value)
                # 约束检查
                if "min" in p.constraints and isinstance(value, (int, float)):
                    if value < p.constraints["min"]:
                        return False, f"参数 {p.name} 不能小于 {p.constraints['min']}"
                if "max" in p.constraints and isinstance(value, (int, float)):
                    if value > p.constraints["max"]:
                        return False, f"参数 {p.name} 不能大于 {p.constraints['max']}"
                if "enum" in p.constraints and value not in p.constraints["enum"]:
                    return False, f"参数 {p.name} 必须是 {p.constraints['enum']} 之一"
                if "pattern" in p.constraints:
                    import re
                    if not re.match(p.constraints["pattern"], str(value)):
                        return False, f"参数 {p.name} 格式不正确"
        return True, None
    
    def get_risk_level(self) -> RiskLevel:
        return self._definition.risk_level
    
    @abstractmethod
    async def execute(self, params: dict, context: dict) -> ToolResult:
        """执行工具"""
        pass
    
    async def pre_execute(self, params: dict, context: dict) -> tuple[bool, Optional[str]]:
        """执行前检查"""
        return True, None
    
    async def post_execute(self, result: ToolResult) -> tuple[bool, Optional[str]]:
        """执行后检查"""
        return True, None
