"""CollaborationAuditLogger - 多Agent协作审计日志 (V3.2 P2)

记录：
- 任务委派事件
- Agent间消息
- 任务完成/失败
- 协作链超时/阻塞
"""
import threading
import time
import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class AuditEvent:
    """审计事件"""
    event_id: str
    session_id: str
    event_type: str          # delegation | message | completion | timeout | error
    timestamp: float
    task_id: str = ""
    agent_id: str = ""
    from_role: str = ""
    to_role: str = ""
    content_preview: str = ""
    metadata: dict = field(default_factory=dict)


class CollaborationAuditLogger:
    """
    协作审计日志

    功能:
    - 记录所有委派、完成、消息事件
    - 支持session级别的日志查询
    - 可导出为JSON Lines格式
    """

    def __init__(self, log_dir: Optional[str] = None):
        self._lock = threading.Lock()
        self._events: list[AuditEvent] = []
        self._log_dir = log_dir
        if log_dir:
            Path(log_dir).mkdir(parents=True, exist_ok=True)

    def log_delegation(
        self,
        session_id: str,
        task_id: str,
        parent_task_id: str,
        from_role: str,
        to_role: str,
        task_preview: str,
    ) -> None:
        """记录委派事件"""
        import uuid
        event = AuditEvent(
            event_id=str(uuid.uuid4())[:12],
            session_id=session_id,
            event_type="delegation",
            timestamp=time.time(),
            task_id=task_id,
            from_role=from_role,
            to_role=to_role,
            content_preview=task_preview,
            metadata={"parent_task_id": parent_task_id},
        )
        self._append(event)

    def log_message(
        self,
        session_id: str,
        task_id: str,
        from_role: str,
        to_role: str,
        msg_type: str,
        content_preview: str,
    ) -> None:
        """记录Agent间消息"""
        import uuid
        event = AuditEvent(
            event_id=str(uuid.uuid4())[:12],
            session_id=session_id,
            event_type="message",
            timestamp=time.time(),
            task_id=task_id,
            from_role=from_role,
            to_role=to_role,
            content_preview=content_preview,
            metadata={"msg_type": msg_type},
        )
        self._append(event)

    def log_completion(
        self,
        session_id: str,
        task_id: str,
        status: str,
        duration_ms: float,
        error: str = "",
    ) -> None:
        """记录任务完成/失败"""
        import uuid
        event = AuditEvent(
            event_id=str(uuid.uuid4())[:12],
            session_id=session_id,
            event_type="completion",
            timestamp=time.time(),
            task_id=task_id,
            content_preview=f"{status} ({duration_ms:.0f}ms)",
            metadata={"duration_ms": duration_ms, "error": error},
        )
        self._append(event)

    def _append(self, event: AuditEvent) -> None:
        with self._lock:
            self._events.append(event)
            if len(self._events) > 10000:
                self._events = self._events[-5000:]

    def get_session_events(
        self,
        session_id: str,
        event_type: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """查询会话事件"""
        with self._lock:
            events = [e for e in self._events if e.session_id == session_id]
            if event_type:
                events = [e for e in events if e.event_type == event_type]
            events = events[-limit:]
            return [asdict(e) for e in events]

    def get_delegation_chain(self, task_id: str) -> list[dict]:
        """获取任务委派链"""
        with self._lock:
            return [
                asdict(e) for e in self._events
                if e.task_id == task_id and e.event_type in ("delegation", "completion")
            ]

    def export_jsonl(self, session_id: str, filepath: str) -> int:
        """导出为JSON Lines格式"""
        events = self.get_session_events(session_id, limit=10000)
        count = 0
        with open(filepath, "w") as f:
            for e in events:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
                count += 1
        logger.info(f"[Audit] Exported {count} events to {filepath}")
        return count

    def get_collaboration_stats(self, session_id: str) -> dict:
        """获取协作统计"""
        events = self.get_session_events(session_id, limit=10000)
        by_type = {}
        for e in events:
            etype = e.get("event_type", "unknown"); by_type[etype] = by_type.get(etype, 0) + 1
        return {
            "session_id": session_id,
            "total_events": len(events),
            "by_type": by_type,
        }


# 全局单例
_audit_logger: Optional[CollaborationAuditLogger] = None


def get_audit_logger() -> CollaborationAuditLogger:
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = CollaborationAuditLogger()
    return _audit_logger
