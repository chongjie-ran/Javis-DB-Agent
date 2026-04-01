"""HookContext - Hook 执行上下文"""
from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime

from .hook_event import HookEvent


@dataclass
class HookContext:
    """
    Hook 执行上下文

    在事件触发时创建，贯穿整个 Hook 执行链。
    包含事件相关的数据和执行状态。
    """

    # 事件信息
    event: HookEvent
    timestamp: datetime = field(default_factory=datetime.now)

    # 会话信息
    session_id: str = ""
    user_id: str = ""
    user_role: str = ""

    # 事件负载数据（由 emit site 填充）
    payload: dict[str, Any] = field(default_factory=dict)

    # 执行状态（由 Hook 处理器填充）
    blocked: bool = False
    blocked_reason: str = ""
    warnings: list[str] = field(default_factory=list)

    # 额外数据
    extra: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        """获取 payload 中的值"""
        return self.payload.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """设置 payload 中的值"""
        self.payload[key] = value

    def set_blocked(self, reason: str) -> None:
        """标记为被拦截"""
        self.blocked = True
        self.blocked_reason = reason

    def add_warning(self, warning: str) -> None:
        """添加警告"""
        self.warnings.append(warning)

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "event": self.event.value,
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
            "user_id": self.user_id,
            "user_role": self.user_role,
            "payload": self.payload,
            "blocked": self.blocked,
            "blocked_reason": self.blocked_reason,
            "warnings": self.warnings,
            "extra": self.extra,
        }
