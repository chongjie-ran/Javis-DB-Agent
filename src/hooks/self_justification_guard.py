"""
自我合理化防护Hook (V3.0 Phase 4)

检测Agent输出中的自我合理化信号（如"能跑就行"、"看起来正确"等），
强制触发验证行动，防止认知捷径和验证跳过。

信号库大小：21个信号词 + 6个开发者特有信号
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .hook_context import AgentHookContext

import logging

from .hook import AgentHook
from .hook_events import AgentHookEvent

logger = logging.getLogger(__name__)


# ── 信号词模式库 ────────────────────────────────────────────────

SELF_JUSTIFICATION_SIGNALS: dict[str, dict[str, str]] = {
    # 认知捷径信号
    "看起来正确": {"severity": "high", "action": "run_validation"},
    "应该没问题": {"severity": "high", "action": "run_validation"},
    "显然": {"severity": "medium", "action": "require_evidence"},
    "显然地": {"severity": "medium", "action": "require_evidence"},
    "必然": {"severity": "high", "action": "run_validation"},
    "毫无疑问": {"severity": "high", "action": "run_validation"},
    "毫无疑问地": {"severity": "high", "action": "run_validation"},

    # 能跑就行信号
    "能跑就行": {"severity": "critical", "action": "block_and_verify"},
    "差不多对了": {"severity": "high", "action": "run_validation"},
    "先跳过": {"severity": "high", "action": "require_justification"},
    "后面再改": {"severity": "medium", "action": "log_risk"},

    # 跳过验证信号
    "先做简单的": {"severity": "high", "action": "redirect_to_hard"},
    "花太久了": {"severity": "high", "action": "require_time_estimate"},
    "大概没问题": {"severity": "high", "action": "run_validation"},
}

# 连续使用信号（连续3次以上触发质疑）
CONTINUOUS_SIGNALS: list[str] = ["显然", "显然地", "必然", "毫无疑问"]

# ── 开发者特有信号 ───────────────────────────────────────────────

DEVELOPER_SIGNALS: dict[str, dict[str, str]] = {
    "能跑就行": {"severity": "critical", "action": "block_and_verify"},
    "先提交后面再测": {"severity": "high", "action": "require_testing_plan"},
    "LeetCode差不多对了": {"severity": "high", "action": "require_submit_proof"},
    "内存泄漏问题不大": {"severity": "critical", "action": "run_valgrind"},
    "这个bug很小先跳过": {"severity": "high", "action": "fix_immediately"},
}

# 合并所有信号库
ALL_SIGNALS: dict[str, dict[str, str]] = {
    **SELF_JUSTIFICATION_SIGNALS,
    **DEVELOPER_SIGNALS,
}


class SelfJustificationGuard(AgentHook):
    """
    自我合理化防护Hook

    检测Agent输出中的自我合理化信号，强制触发验证行动。

    信号严重程度分级：
    - low: 仅记录
    - medium: 记录 + 注入证据请求
    - high: 记录 + 触发特定动作（验证/重定向等）
    - critical: 阻止执行 + 必须完成验证

    连续使用检测：
    - 连续3次使用"显然"、"显然地"、"必然"、"毫无疑问"等词
    - 自动注入质疑，要求提供具体证据

    Attributes:
        severity_threshold: 触发动作的最低严重程度（默认"high"）
        signal_counts: 各信号的连续使用计数
        enabled: 是否启用（默认True）
    """

    name: str = "SelfJustificationGuard"
    priority: int = 50  # 高优先级，在其他hook之前执行

    def __init__(self, severity_threshold: str = "high"):
        """
        初始化自我合理化防护Hook

        Args:
            severity_threshold: 触发动作的最低严重程度
                - "low": 所有信号都触发动作
                - "medium": medium及以上的信号触发动作
                - "high": high及以上的信号触发动作（默认）
                - "critical": 仅critical信号触发动作
        """
        self.severity_threshold = severity_threshold
        self.signal_counts: dict[str, int] = {}
        self.severity_levels: list[str] = ["low", "medium", "high", "critical"]

    def after_iteration(self, ctx: "AgentHookContext") -> "AgentHookContext":
        """
        迭代结束后检测自我合理化信号

        检测逻辑：
        1. 检测信号词（通用 + 开发者特有）
        2. 更新连续使用计数
        3. 根据严重程度触发相应动作
        4. 检查连续使用（>=3次）并注入质疑

        Args:
            ctx: 迭代上下文（含llm_response）

        Returns:
            修改后的ctx（可能设置blocked或注入challenge）
        """
        # 获取要检测的文本（优先使用累积的stream_buffer）
        text = ctx.get_stream_buffer() or ctx.llm_response or ""

        if not text.strip():
            return ctx

        # 1. 检测信号词
        detected = self.detect_signals(text)
        logger.debug(f"[SelfJustificationGuard] 检测到信号: {list(detected.keys())}")

        if not detected:
            # 没有检测到信号，重置所有计数
            self._reset_all_counts()
            return ctx

        # 2. 更新连续使用计数
        self.update_continuous_counts(detected)

        # 3. 检查严重程度并触发动作
        for signal, info in detected.items():
            severity = info["severity"]
            action = info["action"]

            if self._should_trigger_action(severity):
                logger.info(f"[SelfJustificationGuard] 触发动作: signal={signal}, severity={severity}, action={action}")
                self._trigger_action(signal, action, ctx)

        # 4. 检查连续使用（>=3次）
        self._check_continuous_usage(ctx)

        return ctx

    def detect_signals(self, text: str) -> dict[str, dict[str, str]]:
        """
        检测文本中的自我合理化信号

        Args:
            text: 要检测的文本

        Returns:
            检测到的信号字典 {信号词: {severity, action}}
        """
        detected = {}
        for signal, info in ALL_SIGNALS.items():
            if signal in text:
                detected[signal] = info
        return detected

    def update_continuous_counts(self, detected: dict[str, dict[str, str]]) -> None:
        """
        更新信号的连续使用计数

        检测到的信号计数+1，未检测到的信号计数重置为0

        Args:
            detected: 当前迭代检测到的信号字典
        """
        for signal in ALL_SIGNALS:
            if signal in detected:
                self.signal_counts[signal] = self.signal_counts.get(signal, 0) + 1
            else:
                self.signal_counts[signal] = 0

    def _should_trigger_action(self, severity: str) -> bool:
        """
        判断是否应该触发动作

        Args:
            severity: 信号严重程度

        Returns:
            True if 严重程度 >= 阈值
        """
        threshold_idx = self.severity_levels.index(self.severity_threshold)
        severity_idx = self.severity_levels.index(severity)
        return severity_idx >= threshold_idx

    def _trigger_action(self, signal: str, action: str, ctx: "AgentHookContext") -> None:
        """
        触发防护动作

        Args:
            signal: 信号词
            action: 动作类型
            ctx: 上下文
        """
        if action == "run_validation":
            self._inject_validation_request(ctx)
        elif action == "block_and_verify":
            self._block_and_verify(ctx)
        elif action == "require_evidence":
            self._inject_evidence_request(signal, ctx)
        elif action == "redirect_to_hard":
            self._inject_redirect(signal, ctx)
        elif action == "require_time_estimate":
            self._inject_time_request(ctx)
        elif action == "require_justification":
            self._inject_justification_request(signal, ctx)
        elif action == "log_risk":
            self._log_risk(signal, ctx)
        elif action == "require_testing_plan":
            self._inject_testing_plan_request(ctx)
        elif action == "require_submit_proof":
            self._inject_submit_proof_request(ctx)
        elif action == "run_valgrind":
            self._inject_valgrind_request(ctx)
        elif action == "fix_immediately":
            self._inject_fix_immediately_request(signal, ctx)

    def _inject_validation_request(self, ctx: "AgentHookContext") -> None:
        """注入验证请求"""
        ctx.extra["injected_challenge"] = {
            "type": "validation_request",
            "message": "你使用了自我合理化信号。请执行实际验证命令证明你的结论。",
            "severity": "high"
        }

    def _block_and_verify(self, ctx: "AgentHookContext") -> None:
        """阻止并要求验证"""
        ctx.set_blocked("能跑就行信号检测到，必须完成实际验证")
        ctx.extra["injected_challenge"] = {
            "type": "block_and_verify",
            "message": "检测到'能跑就行'信号。此操作被阻止，必须完成实际验证才能继续。",
            "severity": "critical"
        }

    def _inject_evidence_request(self, signal: str, ctx: "AgentHookContext") -> None:
        """注入证据请求"""
        ctx.extra["injected_challenge"] = {
            "type": "evidence_request",
            "message": f"你使用了'{signal}'。请提供至少2个支持你结论的具体证据。",
            "severity": "medium"
        }

    def _inject_redirect(self, signal: str, ctx: "AgentHookContext") -> None:
        """重定向到困难部分"""
        ctx.extra["injected_challenge"] = {
            "type": "redirect",
            "message": "建议先处理最困难的部分，而不是简单的部分。",
            "severity": "high"
        }

    def _inject_time_request(self, ctx: "AgentHookContext") -> None:
        """注入时间估算请求"""
        ctx.extra["injected_challenge"] = {
            "type": "time_estimate",
            "message": "请提供预计完成时间的具体估算，不要说'花太久了'。",
            "severity": "high"
        }

    def _inject_justification_request(self, signal: str, ctx: "AgentHookContext") -> None:
        """注入理由请求"""
        ctx.extra["injected_challenge"] = {
            "type": "justification_request",
            "message": f"你选择'{signal}'。请说明理由和替代方案。",
            "severity": "high"
        }

    def _log_risk(self, signal: str, ctx: "AgentHookContext") -> None:
        """记录风险（不阻止执行）"""
        ctx.add_warning(f"[SelfJustificationGuard] 风险信号: '{signal}'")
        ctx.extra["injected_challenge"] = {
            "type": "risk_log",
            "message": f"检测到风险信号: '{signal}'。请注意此决策的潜在风险。",
            "severity": "medium"
        }

    def _inject_testing_plan_request(self, ctx: "AgentHookContext") -> None:
        """注入测试计划请求（开发者特有）"""
        ctx.extra["injected_challenge"] = {
            "type": "testing_plan_request",
            "message": "你选择'先提交后面再测'。请提供具体的测试计划，包含测试用例和验收标准。",
            "severity": "high"
        }

    def _inject_submit_proof_request(self, ctx: "AgentHookContext") -> None:
        """注入提交证明请求（开发者特有）"""
        ctx.extra["injected_challenge"] = {
            "type": "submit_proof_request",
            "message": "你选择'LeetCode差不多对了'。请提交代码并提供AC截图或运行结果证明。",
            "severity": "high"
        }

    def _inject_valgrind_request(self, ctx: "AgentHookContext") -> None:
        """注入valgrind检查请求（开发者特有）"""
        ctx.set_blocked("检测到'内存泄漏问题不大'信号。必须运行valgrind检查证明无内存泄漏。")
        ctx.extra["injected_challenge"] = {
            "type": "valgrind_request",
            "message": "检测到'内存泄漏问题不大'信号。此操作被阻止，必须运行valgrind证明无内存泄漏。",
            "severity": "critical"
        }

    def _inject_fix_immediately_request(self, signal: str, ctx: "AgentHookContext") -> None:
        """注入立即修复请求（开发者特有）"""
        ctx.extra["injected_challenge"] = {
            "type": "fix_immediately_request",
            "message": f"你选择'{signal}'。请立即修复，不要跳过。",
            "severity": "high"
        }

    def _check_continuous_usage(self, ctx: "AgentHookContext") -> None:
        """检查连续使用并注入质疑"""
        for signal in CONTINUOUS_SIGNALS:
            count = self.signal_counts.get(signal, 0)
            if count >= 3:
                logger.warning(f"[SelfJustificationGuard] 连续使用信号: '{signal}' x{count}")
                ctx.extra["injected_challenge"] = {
                    "type": "continuous_signal_challenge",
                    "message": f"你连续使用了'{signal}'（已连续{count}次）。请提供具体证据支持你的结论，而不是依赖认知捷径。",
                    "severity": "high"
                }
                # 重置计数，防止重复注入
                self.signal_counts[signal] = 0

    def _reset_all_counts(self) -> None:
        """重置所有连续使用计数"""
        for signal in ALL_SIGNALS:
            self.signal_counts[signal] = 0

    def get_signal_counts(self) -> dict[str, int]:
        """获取当前各信号的连续使用计数（用于调试）"""
        return dict(self.signal_counts)

    def get_stats(self) -> dict:
        """获取Hook统计信息"""
        return {
            "name": self.name,
            "enabled": self.enabled,
            "severity_threshold": self.severity_threshold,
            "total_signals": len(ALL_SIGNALS),
            "general_signals": len(SELF_JUSTIFICATION_SIGNALS),
            "developer_signals": len(DEVELOPER_SIGNALS),
            "continuous_signals": len(CONTINUOUS_SIGNALS),
            "current_counts": self.get_signal_counts(),
        }
