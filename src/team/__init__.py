"""多Agent动态协作 (V3.2 P2)
AgentTeamCoordinator: 动态任务委派链 + 消息队列 + 协作审计
"""
from .coordinator import (
    AgentTeamCoordinator,
    get_team_coordinator,
    TaskDelegation,
    AgentMessage,
    CollaborationRole,
)
from .audit import CollaborationAuditLogger, get_audit_logger

__all__ = [
    "AgentTeamCoordinator",
    "get_team_coordinator",
    "TaskDelegation",
    "AgentMessage",
    "CollaborationRole",
    "CollaborationAuditLogger",
    "get_audit_logger",
]
