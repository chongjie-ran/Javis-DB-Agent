"""会话管理
支持持久化，重启后可恢复对话上下文
注意：此文件为兼容层，实际逻辑在 persistent_session.py
"""
from src.gateway.persistent_session import (
    SessionManager,
    Session,
    Message,
    get_session_manager,
    reset_session_manager,
)

# 导出兼容
__all__ = [
    "SessionManager",
    "Session",
    "Message",
    "get_session_manager",
    "reset_session_manager",
]
