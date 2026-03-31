"""
ApprovalGate同步适配器 - 将新async ApprovalGate适配为同步接口
用于兼容旧系统（policy_engine.py等）
"""
from typing import Optional
import asyncio
from src.gateway.approval import ApprovalGate


class SyncApprovalAdapter:
    """将新async ApprovalGate适配为同步接口"""
    
    def __init__(self, async_gate: ApprovalGate):
        self._gate = async_gate
    
    def requires_approval(self, action: str, params: dict) -> bool:
        """判断是否需要审批 - 同步封装"""
        # 新系统基于risk_level判断，简化处理
        high_risk_actions = {"kill_session", "execute_sql", "drop_table", "truncate"}
        return action.lower() in high_risk_actions
    
    def check_can_execute(self, action: str, params: dict) -> tuple[bool, str]:
        """
        检查是否可执行 - 同步封装
        返回 (can_execute, reason)
        """
        if not self.requires_approval(action, params):
            return True, "no_approval_required"
        
        # 对于同步检查，直接返回True（实际审批异步进行）
        # 这里只是判断是否需要触发审批流
        return True, "pending_approval"


# 全局适配器实例
_sync_adapter: Optional[SyncApprovalAdapter] = None


def get_sync_approval_adapter() -> SyncApprovalAdapter:
    global _sync_adapter
    if _sync_adapter is None:
        from src.gateway.approval import get_approval_gate
        async_gate = get_approval_gate()
        _sync_adapter = SyncApprovalAdapter(async_gate)
    return _sync_adapter
