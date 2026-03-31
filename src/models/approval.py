"""
废弃模块 - 请使用 src/gateway/approval.py
废弃日期: 2026-03-31
废弃原因: V2.1已实现新的ApprovalGate，与FastAPI async生态深度集成

双人审批状态机 - L5高风险工具执行前必须完成双人审批
"""
import warnings
warnings.warn(
    "src.models.approval is deprecated (2026-03-31). Use src.gateway.approval instead.",
    DeprecationWarning,
    stacklevel=2,
)

import json
import time
import uuid
import hashlib
from enum import Enum
from typing import Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime


class ApprovalStatus(str, Enum):
    """审批状态"""
    PENDING = "pending"           # 待第一审批人审批
    APPROVED1 = "approved1"       # 第一审批人已通过，待第二审批人
    APPROVED2 = "approved2"       # 双人已通过，可执行
    REJECTED = "rejected"         # 被拒绝
    EXECUTED = "executed"          # 已执行
    EXPIRED = "expired"            # 已过期
    CANCELLED = "cancelled"       # 已取消


# 合法的状态转换
VALID_TRANSITIONS = {
    ApprovalStatus.PENDING: {ApprovalStatus.APPROVED1, ApprovalStatus.REJECTED, ApprovalStatus.CANCELLED, ApprovalStatus.EXPIRED},
    ApprovalStatus.APPROVED1: {ApprovalStatus.APPROVED2, ApprovalStatus.REJECTED, ApprovalStatus.CANCELLED, ApprovalStatus.EXPIRED},
    ApprovalStatus.APPROVED2: {ApprovalStatus.EXECUTED, ApprovalStatus.REJECTED, ApprovalStatus.CANCELLED},
    ApprovalStatus.REJECTED: set(),
    ApprovalStatus.EXECUTED: set(),
    ApprovalStatus.EXPIRED: set(),
    ApprovalStatus.CANCELLED: set(),
}


@dataclass
class ApprovalRecord:
    """审批记录"""
    tool_call_id: str = ""
    tool_name: str = ""
    tool_params: dict = field(default_factory=dict)
    risk_level: int = 0
    requester: str = ""
    reason: str = ""
    # Optional fields with auto-generated defaults
    approval_id: Optional[str] = None
    status: Optional[ApprovalStatus] = None
    approver1: Optional[str] = None
    approver2: Optional[str] = None
    rejector: Optional[str] = None
    rejection_reason: Optional[str] = None
    session_id: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    expires_at: float = 0.0
    executed_at: Optional[float] = None
    execution_result: Optional[str] = None
    # Internal tracking fields (not from user input)
    _approver1_at: float = 0.0
    _approver2_at: float = 0.0
    _executor: str = ""

    def __post_init__(self):
        if self.approval_id is None:
            self.approval_id = str(uuid.uuid4())
        if self.status is None:
            self.status = ApprovalStatus.PENDING
        if self.created_at == 0.0:
            self.created_at = time.time()
        if self.updated_at == 0.0:
            self.updated_at = time.time()

    @property
    def id(self) -> str:
        """Alias for approval_id (for test compatibility)"""
        return self.approval_id

    @property
    def approver1_at(self) -> float:
        """When first approver approved"""
        return self._approver1_at

    @approver1_at.setter
    def approver1_at(self, value: float):
        self._approver1_at = value

    @property
    def approver2_at(self) -> float:
        """When second approver approved"""
        return self._approver2_at

    @approver2_at.setter
    def approver2_at(self, value: float):
        self._approver2_at = value

    @property
    def executor(self) -> str:
        """Who executed the tool"""
        return self._executor

    @executor.setter
    def executor(self, value: str):
        self._executor = value

    @property
    def reject_reason(self) -> Optional[str]:
        """Alias for rejection_reason (for test compatibility)"""
        return self.rejection_reason

    def created_at_str(self) -> str:
        return datetime.fromtimestamp(self.created_at).strftime("%Y-%m-%d %H:%M:%S")

    @property
    def is_executable(self) -> bool:
        return self.status == ApprovalStatus.APPROVED2

    @property
    def is_terminal(self) -> bool:
        return self.status in {ApprovalStatus.REJECTED, ApprovalStatus.EXECUTED, ApprovalStatus.EXPIRED, ApprovalStatus.CANCELLED}

    def can_transition_to(self, new_status: ApprovalStatus) -> bool:
        return new_status in VALID_TRANSITIONS.get(self.status, set())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["_approver1_at"] = self._approver1_at
        d["_approver2_at"] = self._approver2_at
        d["_executor"] = self._executor
        return d


class ApprovalStore:
    def __init__(self, store_path: str = "data/approvals.jsonl"):
        self._store_path = store_path
        self._records: dict[str, ApprovalRecord] = {}
        self._load()

    def _load(self):
        import os
        if not os.path.exists(self._store_path):
            return
        try:
            with open(self._store_path, "r") as f:
                for line in f:
                    if not line.strip():
                        continue
                    d = json.loads(line)
                    d["status"] = ApprovalStatus(d["status"])
                    record = ApprovalRecord(**d)
                    self._records[record.approval_id] = record
        except Exception:
            pass

    def _persist(self, record: ApprovalRecord):
        import os
        os.makedirs(os.path.dirname(self._store_path), exist_ok=True)
        with open(self._store_path, "a") as f:
            f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

    def submit(
        self,
        tool_call_id: str,
        tool_name: str,
        tool_params: dict,
        risk_level: int,
        requester: str,
        reason: str,
        session_id: str = "",
        approver1: Optional[str] = None,
        approver2: Optional[str] = None,
        ttl_seconds: int = 3600,
    ) -> ApprovalRecord:
        # Check for duplicate submission (non-terminal record for same tool_call_id)
        existing = self.get_by_tool_call(tool_call_id)
        if existing:
            raise ValueError(f"已有审批记录: tool_call_id={tool_call_id}")
        now = time.time()
        record = ApprovalRecord(
            approval_id=str(uuid.uuid4()),
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            tool_params=tool_params,
            risk_level=risk_level,
            requester=requester,
            reason=reason,
            status=ApprovalStatus.PENDING,
            session_id=session_id,
            created_at=now,
            updated_at=now,
            expires_at=now + ttl_seconds,
            approver1=approver1,
            approver2=approver2,
        )
        self._records[record.approval_id] = record
        self._persist(record)
        return record

    def get(self, approval_id: str) -> Optional[ApprovalRecord]:
        return self._records.get(approval_id)

    def get_by_tool_call(self, tool_call_id: str) -> Optional[ApprovalRecord]:
        for record in self._records.values():
            if record.tool_call_id == tool_call_id and not record.is_terminal:                return record
        return None

    def approve1(self, approval_id: str, approver1: str) -> ApprovalRecord:
        record = self._records[approval_id]
        record.status = ApprovalStatus.APPROVED1
        record.approver1 = approver1
        record._approver1_at = time.time()
        record.updated_at = time.time()
        self._persist(record)
        return record

    def approve2(self, approval_id: str, approver2: str) -> ApprovalRecord:
        record = self._records[approval_id]
        if record.status != ApprovalStatus.APPROVED1:
            raise ValueError(f"必须先完成第一审批，当前状态: {record.status.value}")
        record.status = ApprovalStatus.APPROVED2
        record.approver2 = approver2
        record._approver2_at = time.time()
        record.updated_at = time.time()
        self._persist(record)
        return record

    def reject(self, approval_id: str, rejector: str, reason: str) -> ApprovalRecord:
        record = self._records[approval_id]
        if record.is_terminal:            raise ValueError(f"审批已终态 {record.status.value}，无法再次拒绝")
        record.status = ApprovalStatus.REJECTED
        record.rejector = rejector
        record.rejection_reason = reason
        record.updated_at = time.time()
        self._persist(record)
        return record

    def mark_executed(self, approval_id: str, executor: str, result: str) -> ApprovalRecord:
        record = self._records[approval_id]
        if record.status != ApprovalStatus.APPROVED2:
            raise ValueError(f"必须先完成双人审批，当前状态: {record.status.value}")
        record.status = ApprovalStatus.EXECUTED
        record._executor = executor
        record.executed_at = time.time()
        record.execution_result = result
        record.updated_at = time.time()
        self._persist(record)
        return record

    def cancel(self, approval_id: str) -> ApprovalRecord:
        record = self._records[approval_id]
        record.status = ApprovalStatus.CANCELLED
        record.updated_at = time.time()
        self._persist(record)
        return record

    def expire_pending(self) -> list[str]:
        now = time.time()
        expired = []
        for record in self._records.values():
            if record.status == ApprovalStatus.PENDING and record.expires_at < now:
                record.status = ApprovalStatus.EXPIRED
                record.updated_at = now
                self._persist(record)
                expired.append(record.approval_id)
        return expired

    def list_pending(self, approver: Optional[str] = None) -> list[ApprovalRecord]:
        self.expire_pending()
        pending = [r for r in self._records.values() if r.status == ApprovalStatus.PENDING]
        if approver:
            pending = [r for r in pending if r.approver1 != approver]
        return pending

    def get_approval_chain(self, session_id: str) -> list[ApprovalRecord]:
        return [
            r for r in self._records.values()
            if r.session_id == session_id
        ]


class ApprovalGate:
    def __init__(self, store: Optional[ApprovalStore] = None):
        self._store = store or ApprovalStore()

    def store(self) -> ApprovalStore:
        return self._store

    def requires_approval(self, risk_level: int) -> bool:
        """L5 only (risk_level == 5) requires approval"""
        return risk_level == 5

    def check_can_execute(self, tool_call_id: str) -> tuple[bool, Optional[str]]:
        # Look for any record (including terminal ones) to report status
        for record in self._store._records.values():
            if record.tool_call_id == tool_call_id:
                if record.is_executable:
                    return True, None
                if record.is_terminal:
                    return False, f"审批状态: {record.status.value}"
                return False, f"待审批状态: {record.status.value}"
        return False, "无审批记录，请先提交审批申请"

    def request_approval(
        self,
        tool_call_id: str,
        tool_name: str,
        tool_params: dict,
        risk_level: int,
        requester: str,
        reason: str,
        session_id: str = "",
        approver1: Optional[str] = None,
        approver2: Optional[str] = None,
        ttl_seconds: int = 3600,
    ) -> ApprovalRecord:
        existing = self._store.get_by_tool_call(tool_call_id)
        if existing:
            raise ValueError(f"已有审批记录: tool_call_id={tool_call_id}")
        return self._store.submit(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            tool_params=tool_params,
            risk_level=risk_level,
            requester=requester,
            reason=reason,
            session_id=session_id,
            approver1=approver1,
            approver2=approver2,
            ttl_seconds=ttl_seconds,
        )

    def is_approved(self, tool_call_id: str) -> bool:
        record = self._store.get_by_tool_call(tool_call_id)
        return record is not None and record.is_executable

    def get_approval_status(self, tool_call_id: str) -> Optional[ApprovalStatus]:
        record = self._store.get_by_tool_call(tool_call_id)
        return record.status if record else None

    def enforce_execution(self, tool_call_id: str, executor: str, result: str) -> ApprovalRecord:
        record = self._store.get_by_tool_call(tool_call_id)
        executed = self._store.mark_executed(record.approval_id, executor, result)
        executed._executor = executor
        return executed


_approval_store: Optional[ApprovalStore] = None


def get_approval_store() -> ApprovalStore:
    global _approval_store
    if _approval_store is None:
        _approval_store = ApprovalStore()
    return _approval_store


_approval_gate: Optional[ApprovalGate] = None


def get_approval_gate() -> ApprovalGate:
    global _approval_gate
    if _approval_gate is None:
        _approval_gate = ApprovalGate()
    return _approval_gate
