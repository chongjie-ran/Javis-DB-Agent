"""AgentHookEvent - Agent生命周期Hook事件枚举 (V3.0 Phase 0)"""

from enum import Enum


class AgentHookEvent(str, Enum):
    """
    Agent层Hook事件类型

    与 gateway/hooks/hook_event.py 的 HookEvent 互补：
    - HookEvent: Tool层（工具执行、SQL检查、审批流程）
    - AgentHookEvent: Agent层（迭代、LLM、流式、验证）

    生命周期顺序：
        before_iteration
          ↓
        before_llm
          ↓
        on_stream  (may repeat)
          ↓
        after_llm
          ↓
        before_execute_tools
          ↓
        after_execute_tools
          ↓
        after_iteration  (loop back to before_iteration if not complete)
          ↓
        on_error (on any exception)
          ↓
        on_complete (when is_complete() returns True)
    """

    # ── 迭代生命周期 ──────────────────────────────────────────
    before_iteration = "agent:before_iteration"
    after_iteration = "agent:after_iteration"

    # ── LLM交互 ───────────────────────────────────────────────
    before_llm = "agent:before_llm"
    after_llm = "agent:after_llm"
    on_stream = "agent:on_stream"

    # ── 工具执行 ──────────────────────────────────────────────
    before_execute_tools = "agent:before_execute_tools"
    after_execute_tools = "agent:after_execute_tools"

    # ── 异常与完成 ────────────────────────────────────────────
    on_error = "agent:on_error"
    on_complete = "agent:on_complete"

    def __str__(self) -> str:
        return self.value

    @property
    def category(self) -> str:
        return self.value.split(":")[0]
