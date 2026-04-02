"""
快速启动辅助函数
快速创建ExploreSpec和ExecuteSpec
"""

from typing import List, Optional
from src.subagent.explore_spec import ExploreSpec
from src.subagent.execute_spec import ExecuteSpec


def quick_explore(task: str) -> ExploreSpec:
    """快速创建探索任务"""
    return ExploreSpec(task=task)


def quick_execute(
    task: str,
    target_files: Optional[List[str]] = None,
    expected_outcome: Optional[str] = None,
    verification: Optional[str] = None,
) -> ExecuteSpec:
    """快速创建执行任务"""
    return ExecuteSpec(
        task=task,
        target_files=target_files,
        expected_outcome=expected_outcome,
        verification_method=verification,
    )
