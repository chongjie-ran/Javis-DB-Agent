"""
AutoVerificationHook - 自动验证Hook (V3.1 P0改进)

Claude Code最佳实践：验证优先 - 给Agent提供验证方式

功能：
- 在after_iteration中自动触发验证
- 检测context中的验证请求
- 强制要求提供验证证据

工作流程：
1. after_iteration被调用
2. 检查context.extra是否有verification_request
3. 如果需要验证但不包含证据，注入质疑
4. 如果包含验证通过标记，记录成功
"""

from typing import Optional
import logging

from .hook import AgentHook
from .hook_context import AgentHookContext

logger = logging.getLogger(__name__)


class AutoVerificationHook(AgentHook):
    """
    自动验证Hook

    核心职责：
    - 检测需要验证的声明
    - 强制要求提供验证证据
    - 阻止未经验证的完成声明

    与AdversarialValidationHook的区别：
    - AdversarialValidationHook: 主动打破假设
    - AutoVerificationHook: 确保验证被实际执行
    """

    name = "auto_verification"
    priority = 40  # 在adversarial之后执行

    def __init__(self, require_evidence: bool = True):
        """
        初始化自动验证Hook

        Args:
            require_evidence: 是否要求提供验证证据（默认True）
        """
        self.require_evidence = require_evidence
        self._verification_stats = {"requested": 0, "verified": 0, "blocked": 0}

    def after_iteration(self, ctx: AgentHookContext) -> AgentHookContext:
        """
        迭代结束后检查验证状态

        Args:
            ctx: 迭代上下文

        Returns:
            修改后的ctx
        """
        # 检查是否需要验证
        verification_needed = ctx.extra.get("verification_request") or ctx.extra.get("requires_verification")

        if not verification_needed:
            return ctx

        self._verification_stats["requested"] += 1

        # 检查是否提供了验证证据
        has_evidence = self._check_verification_evidence(ctx)

        if not has_evidence and self.require_evidence:
            # 未提供证据，注入质疑
            self._inject_verification_challenge(ctx)
            self._verification_stats["blocked"] += 1
            logger.warning(
                f"[AutoVerificationHook] 验证请求但无证据，已注入质疑"
            )
        else:
            # 验证通过
            self._verification_stats["verified"] += 1
            logger.info(f"[AutoVerificationHook] 验证通过")

        return ctx

    def _check_verification_evidence(self, ctx: AgentHookContext) -> bool:
        """
        检查是否提供了验证证据

        证据类型：
        1. ctx.extra["verification_proof"] - 验证命令和结果
        2. ctx.extra["verification_passed"] - 显式验证通过标记
        3. ctx.tool_results - 包含测试/验证命令结果
        """
        # 显式标记
        if ctx.extra.get("verification_passed"):
            return True

        # 验证证据
        proof = ctx.extra.get("verification_proof")
        if proof and len(str(proof)) > 10:  # 证据长度检查
            return True

        # 检查tool_results中的测试结果
        tool_results = ctx.extra.get("tool_results", [])
        for result in tool_results:
            if isinstance(result, dict):
                result_str = str(result.get("result", ""))
                # 检测测试通过标志
                if any(kw in result_str.lower() for kw in ["passed", "success", "ok", "通过"]):
                    return True

        return False

    def _inject_verification_challenge(self, ctx: AgentHookContext) -> None:
        """注入验证质疑"""
        ctx.set_blocked("验证请求但未提供证据，必须执行验证并提供证明")
        ctx.extra["injected_challenge"] = {
            "type": "verification_required",
            "message": "你声明需要验证但未提供验证证据。请执行验证命令并记录：1) 执行的命令 2) 命令输出 3) 通过/失败判定",
            "severity": "critical"
        }

    def get_stats(self) -> dict:
        """获取Hook统计信息"""
        return {
            "name": self.name,
            "require_evidence": self.require_evidence,
            "stats": dict(self._verification_stats),
        }
