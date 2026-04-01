"""HookEvent 枚举定义"""
from enum import Enum


class HookEvent(str, Enum):
    """
    Hook 事件类型枚举

    生命周期分类：
    - Tool: 工具执行生命周期
    - SQL: SQL 专用事件
    - Approval: 审批生命周期
    - Agent: Agent 生命周期
    - Session: 会话生命周期
    """

    # Tool 生命周期
    TOOL_BEFORE_EXECUTE = "tool:before_execute"
    TOOL_AFTER_EXECUTE = "tool:after_execute"
    TOOL_ERROR = "tool:error"

    # SQL 专用
    SQL_BEFORE_GUARD = "sql:before_guard"
    SQL_AFTER_GUARD = "sql:after_guard"
    SQL_DDL_DETECTED = "sql:ddl_detected"

    # 审批生命周期
    APPROVAL_REQUESTED = "approval:requested"
    APPROVAL_APPROVED = "approval:approved"
    APPROVAL_REJECTED = "approval:rejected"

    # Agent 生命周期
    AGENT_BEFORE_INVOKE = "agent:before_invoke"
    AGENT_AFTER_INVOKE = "agent:after_invoke"
    AGENT_ERROR = "agent:error"

    # 会话生命周期
    SESSION_START = "session:start"
    SESSION_END = "session:end"

    def __str__(self) -> str:
        return self.value

    @property
    def category(self) -> str:
        """获取事件类别"""
        return self.value.split(":")[0]
