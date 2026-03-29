"""审计日志 - 哈希链防篡改"""
import json
import time
import uuid
import hashlib
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
    POLICY_CHANGE = "policy.change"
    APPROVAL_REQUEST = "approval.request"
    APPROVAL_GRANT = "approval.grant"
    APPROVAL_REJECT = "approval.reject"
    APPROVAL_EXECUTE = "approval.execute"
    ERROR = "error"


# 创世哈希（第一个哈希基准）
GENESIS_HASH = "0" * 64


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
    # 哈希链字段
    prev_hash: str = ""       # 前一条记录的哈希
    hash: str = ""            # 本条记录的哈希（SHA256）

    @property
    def timestamp_str(self) -> str:
        return datetime.fromtimestamp(self.timestamp).isoformat()

    def _compute_hash(self, prev_hash: str) -> str:
        """计算本条记录的哈希"""
        content = json.dumps({
            "id": self.id,
            "timestamp": self.timestamp,
            "action": self.action.value if isinstance(self.action, AuditAction) else self.action,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "agent_name": self.agent_name,
            "tool_name": self.tool_name,
            "risk_level": self.risk_level,
            "params": self.params,
            "result": self.result,
            "error_message": self.error_message,
            "ip_address": self.ip_address,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
            "prev_hash": prev_hash,
        }, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def seal(self, prev_hash: str):
        """密封记录，绑定前驱哈希并计算自身哈希"""
        self.prev_hash = prev_hash
        self.hash = self._compute_hash(prev_hash)

    def verify(self, prev_hash: str) -> bool:
        """验证本条记录是否被篡改"""
        expected = self._compute_hash(prev_hash)
        return self.hash == expected

    def to_dict(self) -> dict:
        d = asdict(self)
        d["action"] = self.action.value if isinstance(self.action, AuditAction) else self.action
        return d


class AuditLogger:
    """审计日志记录器 - 哈希链防篡改"""

    def __init__(self, log_file: str = "data/audit.jsonl", auto_load: bool = True):
        self._logs: list[AuditLog] = []
        self._log_file = log_file
        self._ensure_storage()
        if auto_load:
            self._load()

    def _ensure_storage(self):
        import os
        os.makedirs("data", exist_ok=True)

    def _load(self):
        """加载已有日志并重建哈希链"""
        import os
        if not os.path.exists(self._log_file):
            return
        prev_hash = GENESIS_HASH
        with open(self._log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    d["action"] = AuditAction(d["action"]) if d["action"] in [a.value for a in AuditAction] else d["action"]
                    record = AuditLog(**d)
                    self._logs.append(record)
                    prev_hash = record.hash
                except Exception:
                    pass

    def _persist(self, log: AuditLog):
        """持久化到文件"""
        import os
        os.makedirs(os.path.dirname(self._log_file), exist_ok=True)
        with open(self._log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log.to_dict(), ensure_ascii=False) + "\n")

    def log(self, log: AuditLog) -> str:
        """记录日志（自动密封哈希链）"""
        prev_hash = self._logs[-1].hash if self._logs else GENESIS_HASH
        log.seal(prev_hash)
        self._logs.append(log)
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
        self.log(log)
        return log

    def verify_chain(self) -> tuple[bool, Optional[str], Optional[int]]:
        """
        验证哈希链完整性
        Returns: (is_valid, error_message, broken_index)
        """
        if not self._logs:
            return True, None, None

        prev_hash = GENESIS_HASH
        for i, record in enumerate(self._logs):
            # 验证前驱哈希匹配
            if record.prev_hash != prev_hash:
                return False, f"记录 {i} 前驱哈希不匹配（期望 {prev_hash[:16]}..., 实际 {record.prev_hash[:16]}...）", i
            # 验证自身哈希完整
            if not record.verify(prev_hash):
                return False, f"记录 {i} 自身哈希不匹配（疑似篡改）", i
            prev_hash = record.hash
        return True, None, None

    def detect_tampering(self, check_from: Optional[float] = None) -> list[dict]:
        """
        篡改检测：返回可疑记录列表
        check_from: 可选，只检查此时间点之后的记录
        """
        suspicious = []
        prev_hash = GENESIS_HASH
        for i, record in enumerate(self._logs):
            if check_from and record.timestamp < check_from:
                prev_hash = record.hash
                continue
            if record.prev_hash != prev_hash:
                suspicious.append({
                    "index": i,
                    "id": record.id,
                    "timestamp": record.timestamp,
                    "reason": "prev_hash_mismatch",
                    "expected_prev": prev_hash[:16] + "...",
                    "actual_prev": record.prev_hash[:16] + "...",
                })
            elif not record.verify(prev_hash):
                suspicious.append({
                    "index": i,
                    "id": record.id,
                    "timestamp": record.timestamp,
                    "reason": "hash_mismatch",
                    "action": record.action.value if isinstance(record.action, AuditAction) else record.action,
                })
            prev_hash = record.hash
        return suspicious

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
            if action and (log.action.value if isinstance(log.action, AuditAction) else log.action) != action.value:
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

    def get_stats(self) -> dict:
        """获取审计统计信息"""
        return {
            "total_records": len(self._logs),
            "first_record": self._logs[0].timestamp_str if self._logs else None,
            "last_record": self._logs[-1].timestamp_str if self._logs else None,
            "genesis_hash": GENESIS_HASH,
            "chain_valid": self.verify_chain()[0],
        }


# 全局单例
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger(log_file: str = "data/audit.jsonl") -> AuditLogger:
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger(log_file=log_file)
    return _audit_logger
