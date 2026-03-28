"""审计日志"""
import json
import time
import uuid
from typing import Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum


class AuditAction(Enum):
    """审计动作类型"""
    SESSION_CREATE = "session.create"
    SESSION_CLOSE = "session.close"
    AGENT_INVOKE = "agent.invoke"
    TOOL_CALL = "tool.call"
    TOOL_RESULT = "tool.result"
    POLICY_PASS = "policy.pass"
    POLICY_DENY = "policy.deny"
    APPROVAL_REQUEST = "approval.request"
    APPROVAL_GRANT = "approval.grant"
    APPROVAL_REJECT = "approval.reject"
    ERROR = "error"


@dataclass
class AuditLog:
    """审计日志条目"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    action: str = ""
    user_id: str = ""
    session_id: str = ""
    agent_name: str = ""
    tool_name: str = ""
    risk_level: int = 0
    params: dict = field(default_factory=dict)
    result: str = ""  # success/failure/denied
    error_message: str = ""
    ip_address: str = ""
    duration_ms: int = 0
    metadata: dict = field(default_factory=dict)
    
    @property
    def timestamp_str(self) -> str:
        return datetime.fromtimestamp(self.timestamp).isoformat()
    
    def to_dict(self) -> dict:
        d = asdict(self)
        d["action"] = self.action.value if isinstance(self.action, AuditAction) else self.action
        return d


class AuditLogger:
    """审计日志记录器"""
    
    def __init__(self, db_path: str = "data/audit.db"):
        self._db_path = db_path
        self._logs: list[AuditLog] = []
        self._log_file = "data/audit.jsonl"
        self._ensure_storage()
    
    def _ensure_storage(self):
        import os
        os.makedirs("data", exist_ok=True)
    
    def log(self, log: AuditLog) -> str:
        """记录日志"""
        self._logs.append(log)
        # 持久化到文件
        self._persist(log)
        return log.id
    
    def log_action(
        self,
        action: AuditAction,
        user_id: str = "",
        session_id: str = "",
        **kwargs
    ) -> AuditLog:
        """快捷记录方法"""
        log = AuditLog(
            action=action,
            user_id=user_id,
            session_id=session_id,
            **kwargs
        )
        return self._logs.append(log) or self._persist(log) or log
    
    def _persist(self, log: AuditLog):
        """持久化到文件"""
        import os
        os.makedirs(os.path.dirname(self._log_file), exist_ok=True)
        with open(self._log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log.to_dict(), ensure_ascii=False) + "\n")
    
    def query(
        self,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        action: Optional[AuditAction] = None,
        tool_name: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        limit: int = 100
    ) -> list[AuditLog]:
        """查询审计日志"""
        results = []
        for log in reversed(self._logs):
            if user_id and log.user_id != user_id:
                continue
            if session_id and log.session_id != session_id:
                continue
            if action and log.action != action.value:
                continue
            if tool_name and log.tool_name != tool_name:
                continue
            if start_time and log.timestamp < start_time:
                continue
            if end_time and log.timestamp > end_time:
                continue
            results.append(log)
            if len(results) >= limit:
                break
        return results
    
    def get_session_audit(self, session_id: str) -> list[AuditLog]:
        """获取会话的所有审计日志"""
        return [log for log in self._logs if log.session_id == session_id]
    
    def get_user_audit(self, user_id: str, hours: int = 24) -> list[AuditLog]:
        """获取用户最近N小时的审计日志"""
        cutoff = time.time() - hours * 3600
        return [log for log in self._logs if log.user_id == user_id and log.timestamp >= cutoff]
    
    def export(self, start_time: float, end_time: float, file_path: str):
        """导出指定时间范围的日志"""
        with open(file_path, "w", encoding="utf-8") as f:
            for log in self._logs:
                if start_time <= log.timestamp <= end_time:
                    f.write(json.dumps(log.to_dict(), ensure_ascii=False) + "\n")


# 全局单例
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
