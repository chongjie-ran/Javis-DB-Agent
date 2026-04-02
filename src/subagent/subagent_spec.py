"""
Subagent规格基类定义
包含 SubagentMode 枚举和 SubagentSpec 抽象基类
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SubagentMode(Enum):
    """Subagent运行模式"""
    EXPLORE = "explore"    # 探索模式：只读快速低成本
    EXECUTE = "execute"    # 执行模式：精确可写


@dataclass
class SubagentSpec(ABC):
    """Subagent规格基类"""
    task: str                    # 任务描述
    timeout: int = 300          # 默认5分钟
    max_cost: int = 50000       # 默认50k token

    @abstractmethod
    def get_instructions(self) -> str:
        """返回给subagent的具体指令"""
        pass

    @abstractmethod
    def validate_result(self, result) -> bool:
        """验证结果是否有效"""
        pass

    @property
    @abstractmethod
    def mode(self) -> SubagentMode:
        """返回Subagent运行模式"""
        pass
