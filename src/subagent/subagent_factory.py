"""Subagent工厂 - P1改进 (V3.2 P0 Tool层集成)

根据SubagentSpec生成subagent运行时配置，工具层从ToolRegistry获取。
"""
from src.subagent.subagent_spec import SubagentMode, SubagentSpec
from src.subagent.explore_spec import ExploreSpec
from src.subagent.execute_spec import ExecuteSpec
from src.subagent.plan_spec import PlanSpec
from src.gateway.tool_registry import get_tool_registry


class SubagentFactory:
    """Subagent工厂（V3.2集成ToolRegistry）"""

    @staticmethod
    def create(spec: SubagentSpec, runtime: str = "subagent") -> dict:
        """创建subagent配置"""
        registry = get_tool_registry()
        
        if spec.mode == SubagentMode.EXPLORE:
            if isinstance(spec, PlanSpec):
                return SubagentFactory._create_plan(spec, registry)
            return SubagentFactory._create_explore(spec, registry)
        else:
            return SubagentFactory._create_execute(spec, registry)

    @staticmethod
    def _create_explore(spec: ExploreSpec, registry) -> dict:
        """创建探索模式subagent"""
        return {
            "runtime": "subagent",
            "mode": "run",
            "runTimeoutSeconds": spec.timeout,
            "task": spec.get_instructions(),
            # 只读工具（从ToolRegistry过滤）
            "tools": {
                "allow": SubagentFactory._get_readonly_tools(registry),
                "deny": ["Bash", "Write", "Edit", "Notebook"],
            },
            "memory": False,
            "is_subagent": True,
            "subagent_mode": "explore",
        }

    @staticmethod
    def _create_plan(spec: PlanSpec, registry) -> dict:
        """创建规划模式subagent"""
        return {
            "runtime": "subagent",
            "mode": "run",
            "runTimeoutSeconds": spec.timeout,
            "task": spec.get_instructions(),
            # 纯只读工具
            "tools": {
                "allow": SubagentFactory._get_readonly_tools(registry),
                "deny": ["Bash", "Write", "Edit", "web_search", "Notebook"],
            },
            "memory": False,
            "is_subagent": True,
            "subagent_mode": "plan",
        }

    @staticmethod
    def _create_execute(spec: ExecuteSpec, registry) -> dict:
        """创建执行模式subagent"""
        return {
            "runtime": "subagent",
            "mode": "run",
            "runTimeoutSeconds": spec.timeout,
            "task": spec.get_instructions(),
            # 允许写操作
            "tools": {
                "allow": SubagentFactory._get_all_write_tools(registry),
                "deny": [],
            },
            "memory": True,
            "is_subagent": True,
            "subagent_mode": "execute",
        }

    @staticmethod
    def _get_readonly_tools(registry) -> list[str]:
        """从ToolRegistry获取只读工具名列表"""
        tools = registry.list_tools(enabled_only=True)
        readonly = []
        for t in tools:
            name = t.get("name", "")
            category = t.get("category", "")
            # query类工具默认只读
            if category == "query":
                readonly.append(name)
        # 确保至少有基础只读工具
        if not readonly:
            readonly = ["Read", "Glob", "Grep"]
        return readonly

    @staticmethod
    def _get_all_write_tools(registry) -> list[str]:
        """从ToolRegistry获取全部可用工具名列表"""
        tools = registry.list_tools(enabled_only=True)
        names = [t.get("name", "") for t in tools]
        # 确保基础工具可用
        base = ["Read", "Write", "Bash", "Glob", "Grep"]
        for b in base:
            if b not in names:
                names.append(b)
        return names
