"""AgentRunSpec - Agent执行规格定义 (V3.0 Phase 1)"""

from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime


@dataclass
class AgentRunSpec:
    """
    Agent执行规格定义

    描述一次Agent执行的目标、约束和上下文信息。

    Attributes:
        goal: 目标描述（用户原始目标）
        context: 上下文字典（会话信息、用户信息、额外数据）
        max_iterations: 最大迭代次数（默认10）
        token_budget: token预算上限（默认10万）
        timeout: 超时秒数（默认3600）
        session_id: 会话ID（从context提取）
        user_id: 用户ID（从context提取）
    """

    goal: str
    context: dict = field(default_factory=dict)
    max_iterations: int = 10
    token_budget: int = 100000
    timeout: int = 3600

    # 辅助属性（从context提取）
    @property
    def session_id(self) -> str:
        return self.context.get("session_id", "")

    @property
    def user_id(self) -> str:
        return self.context.get("user_id", "")

    @property
    def start_time(self) -> datetime:
        return self.context.get("_start_time", datetime.now())

    def is_complete(self) -> bool:
        """
        判断Agent执行是否完成

        完成条件（任一满足即停止）：
        1. 已达成goal（llm_response包含完成标记）
        2. token消耗超过预算
        3. 达到最大迭代次数
        4. 发生错误

        Returns:
            True if execution should stop
        """
        # 检查是否超时
        elapsed = (datetime.now() - self.start_time).total_seconds()
        if elapsed >= self.timeout:
            return True

        return False

    def is_token_over_budget(self, current_tokens: int) -> bool:
        """检查是否超过token预算"""
        return current_tokens >= self.token_budget

    def is_iteration_exhausted(self, current_iteration: int) -> bool:
        """检查是否达到最大迭代次数"""
        return current_iteration >= self.max_iterations

    def with_context(self, **kwargs) -> "AgentRunSpec":
        """
        创建新的AgentRunSpec，合并额外上下文

        Args:
            **kwargs: 要合并的上下文键值对

        Returns:
            新的AgentRunSpec实例
        """
        new_context = {**self.context, **kwargs}
        return AgentRunSpec(
            goal=self.goal,
            context=new_context,
            max_iterations=self.max_iterations,
            token_budget=self.token_budget,
            timeout=self.timeout,
        )
