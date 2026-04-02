"""AgentHookContext - Agent层Hook执行上下文 (V3.0 Phase 0)"""

from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime

from .events import AgentHookEvent


@dataclass
class AgentHookContext:
    """
    Agent层Hook执行上下文

    在AgentRunner.run()的每次迭代中创建，贯穿整个Hook执行链。
    与 gateway/hooks/hook_context.py 的 HookContext 互补（Tool层 vs Agent层）。

    Attributes:
        event: 当前触发的Hook事件
        iteration: 当前迭代编号（从1开始）
        goal: 用户原始目标
        session_id: 会话ID
        user_id: 用户ID
        max_iterations: 最大迭代次数
        token_count: 当前已消耗的token数量
        token_budget: token预算上限
        tools_to_execute: 计划执行的工具列表（before_execute_tools时填充）
        tool_results: 工具执行结果（after_execute_tools时填充）
        llm_response: LLM响应内容（after_llm时填充）
        stream_chunk: 流式chunk（on_stream时填充）
        error: 异常对象（on_error时填充）
        blocked: 是否被某个Hook阻止（由Hook自行设置）
        stop_reason: 停止原因（iteration_limit/token_limit/complete/error）
        extra: 额外数据
    """

    event: AgentHookEvent
    timestamp: datetime = field(default_factory=datetime.now)

    # 迭代信息
    iteration: int = 1
    max_iterations: int = 10

    # 会话信息
    goal: str = ""
    session_id: str = ""
    user_id: str = ""

    # Token管理
    token_count: int = 0
    token_budget: int = 100000  # 默认10万token

    # 工具执行
    tools_to_execute: list[dict] = field(default_factory=list)  # [{"name": "...", "params": {...}}]
    tool_results: list[dict] = field(default_factory=list)      # [{"name": "...", "result": {...}}]

    # LLM交互
    llm_response: str = ""
    stream_chunk: str = ""

    # 异常
    error: Optional[Exception] = None

    # 执行状态（Hook可修改）
    blocked: bool = False
    block_reason: str = ""
    stop_reason: str = ""  # iteration_limit | token_limit | complete | error | hook_blocked
    warnings: list[str] = field(default_factory=list)

    # 额外数据
    extra: dict[str, Any] = field(default_factory=dict)

    # ── 辅助方法 ───────────────────────────────────────────────

    def is_token_over_budget(self) -> bool:
        """检查是否超过token预算"""
        return self.token_count >= self.token_budget

    def is_iteration_exhausted(self) -> bool:
        """检查是否达到最大迭代次数"""
        return self.iteration >= self.max_iterations

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def set_blocked(self, reason: str) -> None:
        self.blocked = True
        self.block_reason = reason
        self.stop_reason = "hook_blocked"

    def get_stream_buffer(self) -> str:
        """获取累积的流式输出（用于after_iteration分析）"""
        return self.stream_chunk

    def to_dict(self) -> dict:
        return {
            "event": self.event.value,
            "timestamp": self.timestamp.isoformat(),
            "iteration": self.iteration,
            "goal": self.goal,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "token_count": self.token_count,
            "token_budget": self.token_budget,
            "tools_to_execute": self.tools_to_execute,
            "tool_results": self.tool_results,
            "llm_response": self.llm_response,
            "blocked": self.blocked,
            "block_reason": self.block_reason,
            "stop_reason": self.stop_reason,
            "warnings": self.warnings,
            "extra": self.extra,
        }
