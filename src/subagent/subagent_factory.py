"""
Subagent工厂
根据SubagentSpec生成subagent运行时配置
"""

from src.subagent.subagent_spec import SubagentMode, SubagentSpec
from src.subagent.explore_spec import ExploreSpec
from src.subagent.execute_spec import ExecuteSpec


class SubagentFactory:
    """Subagent工厂"""

    @staticmethod
    def create(spec: SubagentSpec, runtime: str = "subagent") -> dict:
        """创建subagent配置"""
        if spec.mode == SubagentMode.EXPLORE:
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
            # 限制工具使用：只读工具
            "tools": {
                "allow": ["read", "exec", "web_search"],
                "deny": ["write", "edit", "delete"],
            },
            "memory": False,  # 探索不需要长期记忆
            "is_subagent": True,
            "subagent_mode": "explore",
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
                "allow": ["read", "write", "exec"],
                "deny": [],
            },
            "memory": True,  # 执行需要记忆
            "is_subagent": True,
            "subagent_mode": "execute",
        }
