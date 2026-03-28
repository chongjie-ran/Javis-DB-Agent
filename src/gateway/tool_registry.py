"""工具注册中心"""
from typing import Optional, Callable, Any
from dataclasses import dataclass
from src.tools.base import BaseTool, ToolDefinition, ToolResult, RiskLevel


@dataclass
class ToolMetadata:
    """工具元数据"""
    tool: BaseTool
    enabled: bool = True
    call_count: int = 0
    total_time_ms: int = 0
    
    @property
    def avg_time_ms(self) -> int:
        if self.call_count == 0:
            return 0
        return self.total_time_ms // self.call_count


class ToolRegistry:
    """工具注册中心"""
    
    def __init__(self):
        self._tools: dict[str, ToolMetadata] = {}
    
    def register(self, tool: BaseTool, enabled: bool = True) -> None:
        """注册工具"""
        self._tools[tool.name] = ToolMetadata(tool=tool, enabled=enabled)
    
    def unregister(self, name: str) -> bool:
        """注销工具"""
        return self._tools.pop(name, None) is not None
    
    def get_tool(self, name: str) -> Optional[BaseTool]:
        """获取工具实例"""
        meta = self._tools.get(name)
        return meta.tool if meta else None
    
    def get_metadata(self, name: str) -> Optional[ToolMetadata]:
        """获取工具元数据"""
        return self._tools.get(name)
    
    def list_tools(self, enabled_only: bool = False, category: Optional[str] = None) -> list[ToolDefinition]:
        """列出工具定义"""
        result = []
        for meta in self._tools.values():
            if enabled_only and not meta.enabled:
                continue
            defn = meta.tool.definition_dict
            if category and defn.get("category") != category:
                continue
            result.append(defn)
        return result
    
    def list_tool_names(self, enabled_only: bool = False, category: Optional[str] = None) -> list[str]:
        """列出工具名称"""
        result = []
        for name, meta in self._tools.items():
            if enabled_only and not meta.enabled:
                continue
            defn = meta.tool.definition_dict
            if category and defn.get("category") != category:
                continue
            result.append(name)
        return result
    
    def enable(self, name: str) -> bool:
        """启用工具"""
        meta = self._tools.get(name)
        if meta:
            meta.enabled = True
            return True
        return False
    
    def disable(self, name: str) -> bool:
        """禁用工具"""
        meta = self._tools.get(name)
        if meta:
            meta.enabled = False
            return True
        return False
    
    def get_by_category(self, category: str) -> list[BaseTool]:
        """按类别获取工具"""
        result = []
        for meta in self._tools.values():
            if meta.enabled and meta.tool.definition_dict.get("category") == category:
                result.append(meta.tool)
        return result
    
    def get_tools_by_risk(self, max_risk: RiskLevel) -> list[BaseTool]:
        """获取不超过指定风险级别的工具"""
        result = []
        for meta in self._tools.values():
            if meta.enabled and meta.tool.get_risk_level() <= max_risk:
                result.append(meta.tool)
        return result
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "total": len(self._tools),
            "enabled": sum(1 for m in self._tools.values() if m.enabled),
            "by_category": {
                cat: sum(1 for m in self._tools.values() 
                        if m.enabled and m.tool.definition_dict.get("category") == cat)
                for cat in ["query", "analysis", "action"]
            },
            "top_called": sorted(
                [(n, m.call_count) for n, m in self._tools.items()],
                key=lambda x: -x[1]
            )[:10]
        }


# 全局单例
_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
