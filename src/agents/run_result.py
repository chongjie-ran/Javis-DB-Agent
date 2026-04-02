"""RunResult - Agent执行结果 (V3.0 Phase 1)"""

from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime

from src.hooks.hook_context import AgentHookContext


@dataclass
class RunResult:
    """
    Agent执行结果

    封装Agent执行完成后的完整结果信息。

    Attributes:
        context: 最后的Hook执行上下文
        success: 执行是否成功
        output: 最终输出内容
        iterations: 实际迭代次数
        tokens_used: 实际使用的token数量
        errors: 执行过程中发生的错误列表
        duration_ms: 总执行时间（毫秒）
        stop_reason: 停止原因（complete/token_limit/iteration_limit/timeout/error/hook_blocked）
        metadata: 额外元数据
    """

    context: AgentHookContext
    success: bool = False
    output: str = ""
    iterations: int = 0
    tokens_used: int = 0
    errors: list = field(default_factory=list)
    duration_ms: int = 0
    stop_reason: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def goal(self) -> str:
        """获取原始目标"""
        return self.context.goal if self.context else ""

    @property
    def session_id(self) -> str:
        """获取会话ID"""
        return self.context.session_id if self.context else ""

    @property
    def user_id(self) -> str:
        """获取用户ID"""
        return self.context.user_id if self.context else ""

    @property
    def warnings(self) -> list:
        """获取所有警告"""
        return self.context.warnings if self.context else []

    @property
    def tool_results(self) -> list:
        """获取工具执行结果"""
        return self.context.tool_results if self.context else []

    @property
    def llm_response(self) -> str:
        """获取LLM响应"""
        return self.context.llm_response if self.context else ""

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "success": self.success,
            "output": self.output,
            "iterations": self.iterations,
            "tokens_used": self.tokens_used,
            "errors": self.errors,
            "duration_ms": self.duration_ms,
            "stop_reason": self.stop_reason,
            "goal": self.goal,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }

    def __str__(self) -> str:
        """友好的字符串表示"""
        status = "✓ 成功" if self.success else "✗ 失败"
        return (
            f"RunResult({status}, "
            f"iterations={self.iterations}, "
            f"tokens={self.tokens_used}, "
            f"stop={self.stop_reason})"
        )
