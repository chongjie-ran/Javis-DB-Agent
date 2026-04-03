"""
Subagent工厂 - P1改进
根据SubagentSpec生成subagent运行时配置

改进点（V3.1）：
- 支持PlanSpec（规划模式）
- 增强只读约束
"""

from src.subagent.subagent_spec import SubagentMode, SubagentSpec
from src.subagent.explore_spec import ExploreSpec
from src.subagent.execute_spec import ExecuteSpec
from src.subagent.plan_spec import PlanSpec


class SubagentFactory:
    """Subagent工厂"""

    @staticmethod
    def create(spec: SubagentSpec, runtime: str = "subagent") -> dict:
        """创建subagent配置"""
        if spec.mode == SubagentMode.EXPLORE:
            if isinstance(spec, PlanSpec):
                return SubagentFactory._create_plan(spec)
            return SubagentFactory._create_explore(spec)
        else:
            return SubagentFactory._create_execute(spec)

    @staticmethod
    def _create_explore(spec: ExploreSpec) -> dict:
        """创建探索模式subagent"""
        return {
            "runtime": "subagent",
            "mode": "run",
            "runTimeoutSeconds": spec.timeout,
            "task": spec.get_instructions(),
            # 只读工具
            "tools": {
                "allow": ["Read", "Glob", "Grep", "web_search"],
                "deny": ["Bash", "Write", "Edit", "Notebook"],
            },
            "memory": False,  # 探索不需要长期记忆
            "is_subagent": True,
            "subagent_mode": "explore",
        }

    @staticmethod
    def _create_plan(spec: PlanSpec) -> dict:
        """创建规划模式subagent"""
        return {
            "runtime": "subagent",
            "mode": "run",
            "runTimeoutSeconds": spec.timeout,
            "task": spec.get_instructions(),
            # 纯只读工具（比Explore更严格）
            "tools": {
                "allow": ["Read", "Glob", "Grep"],
                "deny": ["Bash", "Write", "Edit", "web_search", "Notebook"],
            },
            "memory": False,  # 规划不需要长期记忆
            "is_subagent": True,
            "subagent_mode": "plan",
        }

    @staticmethod
    def _create_execute(spec: ExecuteSpec) -> dict:
        """创建执行模式subagent"""
        return {
            "runtime": "subagent",
            "mode": "run",
            "runTimeoutSeconds": spec.timeout,
            "task": spec.get_instructions(),
            # 允许写操作
            "tools": {
                "allow": ["Read", "Write", "Bash", "Glob", "Grep"],
                "deny": [],
            },
            "memory": True,  # 执行需要记忆
            "is_subagent": True,
            "subagent_mode": "execute",
        }
