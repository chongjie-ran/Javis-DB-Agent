"""双人审批状态机 - L5高风险工具执行前必须完成双人审批"""
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
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tool_call_id: str = ""                    # 关联的工具调用ID
    status: ApprovalStatus = ApprovalStatus.PENDING
    # 工具信息
    tool_name: str = ""
    tool_params: dict = field(default_factory=dict)
    risk_level: int = 5                        # 默认为L5
    # 审批人
    approver1: Optional[str] = None            # 第一审批人（通常是直接主管）
    approver2: Optional[str] = None            # 第二审批人（通常是安全/运维负责人）
    approver1_at: Optional[float] = None      # 第一审批时间
    approver2_at: Optional[float] = None      # 第二审批时间
    rejector: Optional[str] = None             # 拒绝人
    rejected_at: Optional[float] = None        # 拒绝时间
    reject_reason: str = ""                    # 拒绝原因
    # 时间戳
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    # 执行信息
    executed_at: Optional[float] = None
    executor: Optional[str] = None
    execution_result: str = ""                 # 执行结果摘要
    # 额外信息
    requester: str = ""                        # 申请人
    reason: str = ""                           # 申请理由
    session_id: str = ""
    expires_at: float = field(default_factory=lambda: time.time() + 3600)  # 1小时后过期

    @property
    def created_at_str(self) -> str:
        return datetime.fromtimestamp(self.created_at).isoformat()

    @property
    def is_executable(self) -> bool:
        """是否可以执行"""
        return self.status == ApprovalStatus.APPROVED2

    @property
    def is_terminal(self) -> bool:
        """是否为终态"""
        return self.status in {ApprovalStatus.REJECTED, ApprovalStatus.EXECUTED, ApprovalStatus.EXPIRED, ApprovalStatus.CANCELLED}

    def can_transition_to(self, new_status: ApprovalStatus) -> bool:
        """检查状态转换是否合法"""
        return new_status in VALID_TRANSITIONS.get(self.status, set())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["is_executable"] = self.is_executable
        d["is_terminal"] = self.is_terminal
        return d


class ApprovalStore:
    """审批存储管理器（内存+文件持久化）"""

    def __init__(self, store_path: str = "data/approvals.jsonl"):
        import os
        self._store_path = store_path
        os.makedirs(os.path.dirname(store_path), exist_ok=True)
        self._records: dict[str, ApprovalRecord] = {}
        self._by_tool_call: dict[str, str] = {}  # tool_call_id -> approval_id
        self._load()

    def _load(self):
        """从文件加载已有记录"""
        import os
        if not os.path.exists(self._store_path):
            return
        with open(self._store_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    d["status"] = ApprovalStatus(d["status"])
                    record = ApprovalRecord(**d)
                    self._records[record.id] = record
                    if record.tool_call_id:
                        self._by_tool_call[record.tool_call_id] = record.id
                except Exception:
                    pass

    def _persist(self, record: ApprovalRecord):
        """持久化单条记录"""
        with open(self._store_path, "a", encoding="utf-8") as f:
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
        """提交审批申请"""
        if tool_call_id in self._by_tool_call:
            existing_id = self._by_tool_call[tool_call_id]
            raise ValueError(f"该工具调用已有审批记录: {existing_id}")

        record = ApprovalRecord(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            tool_params=tool_params,
            risk_level=risk_level,
            requester=requester,
            reason=reason,
            session_id=session_id,
            approver1=approver1,
            approver2=approver2,
            expires_at=time.time() + ttl_seconds,
        )
        self._records[record.id] = record
        self._by_tool_call[tool_call_id] = record.id
        self._persist(record)
        return record

    def get(self, approval_id: str) -> Optional[ApprovalRecord]:
        """通过ID获取审批记录"""
        return self._records.get(approval_id)

    def get_by_tool_call(self, tool_call_id: str) -> Optional[ApprovalRecord]:
        """通过工具调用ID获取审批记录"""
        aid = self._by_tool_call.get(tool_call_id)
        return self._records.get(aid) if aid else None

    def approve1(self, approval_id: str, approver1: str) -> ApprovalRecord:
        """第一审批人审批"""
        record = self._records.get(approval_id)
        if not record:
            raise ValueError(f"审批记录不存在: {approval_id}")
        if not record.can_transition_to(ApprovalStatus.APPROVED1):
            raise ValueError(f"当前状态 {record.status.value} 不允许第一审批")
        if record.approver1 and record.approver1 != approver1:
            raise ValueError(f"第一审批人应为: {record.approver1}")

        record.status = ApprovalStatus.APPROVED1
        record.approver1 = approver1
        record.approver1_at = time.time()
        record.updated_at = time.time()
        self._persist(record)
        return record

    def approve2(self, approval_id: str, approver2: str) -> ApprovalRecord:
        """第二审批人审批"""
        record = self._records.get(approval_id)
        if not record:
            raise ValueError(f"审批记录不存在: {approval_id}")
        if record.status != ApprovalStatus.APPROVED1:
            raise ValueError(f"当前状态 {record.status.value} 必须先完成第一审批")
        if record.approver2 and record.approver2 != approver2:
            raise ValueError(f"第二审批人应为: {record.approver2}")

        record.status = ApprovalStatus.APPROVED2
        record.approver2 = approver2
        record.approver2_at = time.time()
        record.updated_at = time.time()
        self._persist(record)
        return record

    def reject(self, approval_id: str, rejector: str, reason: str) -> ApprovalRecord:
        """拒绝审批"""
        record = self._records.get(approval_id)
        if not record:
            raise ValueError(f"审批记录不存在: {approval_id}")
        if record.is_terminal:
            raise ValueError(f"当前状态 {record.status.value} 为终态，无法拒绝")

        record.status = ApprovalStatus.REJECTED
        record.rejector = rejector
        record.rejected_at = time.time()
        record.reject_reason = reason
        record.updated_at = time.time()
        self._persist(record)
        return record

    def mark_executed(self, approval_id: str, executor: str, result: str) -> ApprovalRecord:
        """标记为已执行"""
        record = self._records.get(approval_id)
        if not record:
            raise ValueError(f"审批记录不存在: {approval_id}")
        if record.status != ApprovalStatus.APPROVED2:
            raise ValueError(f"当前状态 {record.status.value} 必须先完成双人审批才能执行")

        record.status = ApprovalStatus.EXECUTED
        record.executor = executor
        record.executed_at = time.time()
        record.execution_result = result
        record.updated_at = time.time()
        self._persist(record)
        return record

    def cancel(self, approval_id: str) -> ApprovalRecord:
        """取消审批"""
        record = self._records.get(approval_id)
        if not record:
            raise ValueError(f"审批记录不存在: {approval_id}")
        if record.is_terminal:
            raise ValueError(f"当前状态 {record.status.value} 为终态，无法取消")

        record.status = ApprovalStatus.CANCELLED
        record.updated_at = time.time()
        self._persist(record)
        return record

    def expire_pending(self) -> list[str]:
        """使所有已过期的pending/apprvoed1记录过期"""
        expired_ids = []
        now = time.time()
        for record in self._records.values():
            if record.status in {ApprovalStatus.PENDING, ApprovalStatus.APPROVED1}:
                if record.expires_at < now:
                    record.status = ApprovalStatus.EXPIRED
                    record.updated_at = now
                    self._persist(record)
                    expired_ids.append(record.id)
        return expired_ids

    def list_pending(self, approver: Optional[str] = None) -> list[ApprovalRecord]:
        """列出待审批记录"""
        results = []
        for record in self._records.values():
            if record.is_terminal:
                continue
            if approver:
                # 如果指定审批人，只看该人需要审批的
                if record.status == ApprovalStatus.PENDING:
                    if record.approver1 and record.approver1 != approver:
                        continue
                elif record.status == ApprovalStatus.APPROVED1:
                    if record.approver2 and record.approver2 != approver:
                        continue
                else:
                    continue
            results.append(record)
        return sorted(results, key=lambda r: r.created_at)

    def get_approval_chain(self, session_id: str) -> list[ApprovalRecord]:
        """获取某会话的所有审批记录"""
        return [r for r in self._records.values() if r.session_id == session_id]


# ---------------------------------------------------------------------------
# 审批门卫 - 集成到PolicyEngine
# ---------------------------------------------------------------------------

class ApprovalGate:
    """审批门卫：L5工具执行前检查审批状态"""

    def __init__(self, store: Optional[ApprovalStore] = None):
        self._store = store or ApprovalStore()

    @property
    def store(self) -> ApprovalStore:
        return self._store

    def requires_approval(self, risk_level: int) -> bool:
        """判断是否需要审批"""
        return risk_level >= 5

    def check_can_execute(self, tool_call_id: str) -> tuple[bool, Optional[str]]:
        """检查工具调用是否可以执行（已完成双人审批）"""
        record = self._store.get_by_tool_call(tool_call_id)
        if not record:
            return False, "无审批记录"
        if not record.is_executable:
            return False, f"审批状态: {record.status.value}，需要双人审批通过"
        return True, None

    def enforce_execution(self, tool_call_id: str, executor: str, result: str) -> ApprovalRecord:
        """强制执行后标记"""
        return self._store.mark_executed(tool_call_id, executor, result)


# 全局单例
_approval_store: Optional[ApprovalStore] = None
_approval_gate: Optional[ApprovalGate] = None


def get_approval_store() -> ApprovalStore:
    global _approval_store
    if _approval_store is None:
        _approval_store = ApprovalStore()
    return _approval_store


def get_approval_gate() -> ApprovalGate:
    global _approval_gate
    if _approval_gate is None:
        _approval_gate = ApprovalGate(get_approval_store())
    return _approval_gate
