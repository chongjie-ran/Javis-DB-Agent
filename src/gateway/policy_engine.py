"""策略引擎 - 安全策略执行"""
import time
from typing import Optional
from enum import IntEnum
from dataclasses import dataclass, field
from src.tools.base import RiskLevel
from src.models.approval import get_approval_gate, ApprovalGate


class UserRole(IntEnum):
    """用户角色"""
    VIEWER = 1      # 查看
    ANALYST = 2     # 分析
    ADVISOR = 3     # 建议
    OPERATOR = 4    # 执行
    ADMIN = 5       # 管理员


# 角色与风险级别权限映射
ROLE_PERMISSIONS = {
    UserRole.VIEWER: [RiskLevel.L1_READ],
    UserRole.ANALYST: [RiskLevel.L1_READ, RiskLevel.L2_DIAGNOSE],
    UserRole.ADVISOR: [RiskLevel.L1_READ, RiskLevel.L2_DIAGNOSE, RiskLevel.L3_LOW_RISK],
    UserRole.OPERATOR: [RiskLevel.L1_READ, RiskLevel.L2_DIAGNOSE, RiskLevel.L3_LOW_RISK, RiskLevel.L4_MEDIUM],
    UserRole.ADMIN: [RiskLevel.L1_READ, RiskLevel.L2_DIAGNOSE, RiskLevel.L3_LOW_RISK, RiskLevel.L4_MEDIUM, RiskLevel.L5_HIGH],
}


@dataclass
class PolicyContext:
    """策略检查上下文"""
    user_id: str
    user_role: UserRole = UserRole.VIEWER
    user_name: str = ""
    session_id: str = ""
    ip_address: str = ""
    user_agent: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class PolicyResult:
    """策略检查结果"""
    allowed: bool
    reason: str = ""
    approval_required: bool = False
    approvers: list[str] = field(default_factory=list)


class PolicyEngine:
    """策略引擎"""
    
    def __init__(self, approval_gate: Optional[ApprovalGate] = None):
        self._custom_rules: list[callable] = []
        self._require_approval_l4 = True
        self._require_dual_approval_l5 = True
        self._approval_gate = approval_gate
        self._version: int = 1
        self._version_history: list[dict] = [{"version": 1, "timestamp": time.time(), "change": "initial"}]

    @property
    def approval_gate(self) -> ApprovalGate:
        """获取审批门卫"""
        if self._approval_gate is None:
            self._approval_gate = get_approval_gate()
        return self._approval_gate
    
    def set_approval_config(self, l4: bool = True, l5: bool = True):
        """设置审批配置"""
        old_l4 = self._require_approval_l4
        old_l5 = self._require_dual_approval_l5
        self._require_approval_l4 = l4
        self._require_dual_approval_l5 = l5
        
        # 记录变更
        if old_l4 != l4 or old_l5 != l5:
            self._version += 1
            self._version_history.append({
                "version": self._version,
                "timestamp": time.time(),
                "change": f"approval_config: l4={old_l4}->{l4}, l5={old_l5}->{l5}",
                "l4_required": l4,
                "l5_dual_required": l5,
            })
            # 记录到审计日志
            try:
                from src.gateway.audit import get_audit_logger, AuditAction
                audit = get_audit_logger()
                audit.log_action(
                    action=AuditAction.POLICY_CHANGE,
                    user_id="system",
                    metadata={
                        "l4_required": {"old": old_l4, "new": l4},
                        "l5_dual_required": {"old": old_l5, "new": l5},
                        "new_version": self._version,
                    }
                )
            except Exception:
                pass
    
    def get_version(self) -> int:
        """获取当前策略版本"""
        return self._version
    
    def get_version_history(self, limit: int = 50) -> list[dict]:
        """获取策略版本历史"""
        return self._version_history[-limit:]
    
    def add_rule(self, rule: callable):
        """添加自定义规则（同时增加版本号）"""
        self._custom_rules.append(rule)
        self._version += 1
        self._version_history.append({
            "version": self._version,
            "timestamp": time.time(),
            "change": f"added_custom_rule: {rule.__name__ if hasattr(rule, '__name__') else 'anonymous'}",
        })
    
    def check(self, context: PolicyContext, action: str, risk_level: RiskLevel) -> PolicyResult:
        """安全检查"""
        # 1. 检查角色权限
        allowed_levels = ROLE_PERMISSIONS.get(context.user_role, [])
        if risk_level not in allowed_levels:
            return PolicyResult(
                allowed=False,
                reason=f"角色 {context.user_role.name} 无权执行风险级别 {risk_level.name} 的操作"
            )
        
        # 2. 检查自定义规则
        for rule in self._custom_rules:
            try:
                result = rule(context, action, risk_level)
                if isinstance(result, PolicyResult):
                    return result
            except Exception:
                pass
        
        # 3. 确定是否需要审批
        approval_required = False
        approvers = []
        if risk_level == RiskLevel.L4_MEDIUM and self._require_approval_l4:
            approval_required = True
            approvers = ["审批人"]
        elif risk_level == RiskLevel.L5_HIGH and self._require_dual_approval_l5:
            approval_required = True
            approvers = ["审批人1", "审批人2"]
        
        return PolicyResult(
            allowed=True,
            approval_required=approval_required,
            approvers=approvers
        )
    
    def can_auto_handle(self, risk_level: RiskLevel) -> bool:
        """判断是否可自动处置"""
        return risk_level <= RiskLevel.L3_LOW_RISK
    
    def get_risk_description(self, risk_level: RiskLevel) -> str:
        """获取风险级别描述"""
        descriptions = {
            RiskLevel.L1_READ: "只读分析，无需审批",
            RiskLevel.L2_DIAGNOSE: "自动诊断，无需审批",
            RiskLevel.L3_LOW_RISK: "低风险执行，仅日志记录",
            RiskLevel.L4_MEDIUM: "中风险执行，需单签审批",
            RiskLevel.L5_HIGH: "高风险执行，需双人审批",
        }
        return descriptions.get(risk_level, "未知风险")

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
    ):
        """提交L5工具的审批申请"""
        return self.approval_gate.request_approval(
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


# 全局单例
_policy_engine: Optional[PolicyEngine] = None


def get_policy_engine() -> PolicyEngine:
    global _policy_engine
    if _policy_engine is None:
        _policy_engine = PolicyEngine()
    return _policy_engine
