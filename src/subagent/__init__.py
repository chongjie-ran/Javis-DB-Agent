"""
Javis-DB-Agent Subagent Module
三模式Subagent系统：Explore（探索）、Plan（规划）、Execute（执行）

改进（V3.1）：
- 新增PlanSpec（规划模式）
- 增强只读约束
"""

from src.subagent.subagent_spec import SubagentMode, SubagentSpec
from src.subagent.explore_spec import ExploreSpec
from src.subagent.execute_spec import ExecuteSpec
from src.subagent.plan_spec import PlanSpec
from src.subagent.subagent_factory import SubagentFactory
from src.subagent.hooks import SubagentModeHook
from src.subagent.helpers import quick_explore, quick_execute

__all__ = [
    "SubagentMode",
    "SubagentSpec",
    "ExploreSpec",
    "ExecuteSpec",
    "PlanSpec",
    "SubagentFactory",
    "SubagentModeHook",
    "quick_explore",
    "quick_execute",
]
