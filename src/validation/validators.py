"""
内置验证器集合 (V3.0 Phase 3)

包含三个核心验证器：
1. CompletionClaimValidator - 检测"完成声明"，触发对抗性验证
2. SQLBoundaryValidator - 构造SQL边界条件，打破"SQL安全"假设
3. TokenOverBudgetValidator - 检查Token是否超预算

使用示例：
    from src.validation import get_validator_registry, CompletionClaimValidator

    registry = get_validator_registry()
    registry.register("completion_claim", CompletionClaimValidator())

    context = ctx.to_dict()  # AgentHookContext.to_dict()
    result = registry.validate(context, "completion_claim")
    if result.broken:
        # 发现完成声明，需要对抗性验证
"""

import re
import logging
from typing import Optional

from .validator_registry import (
    Validator,
    BreakingValidator,
    ValidationResult,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# CompletionClaimValidator - 检测完成声明
# ─────────────────────────────────────────────────────────────────────────────

class CompletionClaimValidator(Validator):
    """
    检测LLM输出的"完成声明"

    目的：LLM可能在没有真正完成时声称"已完成"，需要触发对抗性验证。

    完成声明信号词：
    - 直接声明："任务完成"、"已完成"、"搞定"
    - 模糊声明："已经好了"、"没问题了"
    - 结论性声明："综上所述"、"总结一下"
    - 行动声明："已经执行"、"已经修复"

    注意：
    - 这个验证器只是检测，不直接阻止
    - 检测到后应由AgentRunner决定是否触发对抗性验证
    - 高置信度需要多个信号叠加

    设计：Validator而非BreakingValidator，因为只是"检测"而非"打破"
    """

    name = "completion_claim"
    enabled = True

    # 完成声明信号词（按置信度分类）
    HIGH_CONFIDENCE_SIGNALS = [
        r"任务完成",
        r"已经完成",
        r"完成修复",
        r"搞定",
        r"问题已解决",
        r"已完成所有",
        r"全部完成",
    ]

    MEDIUM_CONFIDENCE_SIGNALS = [
        r"已经好了",
        r"没问题了",
        r"处理完了",
        r"搞定了",
        r"已经搞定",
        r"修复完成",
        r"执行完毕",
        r"已经执行",
    ]

    LOW_CONFIDENCE_SIGNALS = [
        r"综上所述",
        r"总结一下",
        r"总之",
        r"结论是",
        r"看起来没问题",
        r"应该可以了",
        r"大概好了",
        r"差不多完成",
    ]

    def __init__(self, confidence_threshold: float = 0.6):
        """
        Args:
            confidence_threshold: 置信度阈值（0-1），超过则报告broken
        """
        self.confidence_threshold = confidence_threshold

    def validate(self, context: dict) -> ValidationResult:
        text = context.get("llm_response", "")
        if not text:
            return ValidationResult(broken=False, validator_name=self.name)

        # 计算置信度
        score = self._calculate_confidence(text)

        if score >= self.confidence_threshold:
            matched_signals = self._find_matched_signals(text)
            return ValidationResult(
                broken=True,
                validator_name=self.name,
                reason=f"检测到完成声明（置信度={score:.2f}）",
                evidence=f"匹配信号: {', '.join(matched_signals[:3])}",
                suggestion="请进行对抗性验证：检查是否真的完成",
                severity="warning",
            )

        return ValidationResult(broken=False, validator_name=self.name)

    def _calculate_confidence(self, text: str) -> float:
        """计算完成声明置信度（0-1）"""
        score = 0.0

        for pattern in self.HIGH_CONFIDENCE_SIGNALS:
            if re.search(pattern, text):
                score += 0.4

        for pattern in self.MEDIUM_CONFIDENCE_SIGNALS:
            if re.search(pattern, text):
                score += 0.25

        for pattern in self.LOW_CONFIDENCE_SIGNALS:
            if re.search(pattern, text):
                score += 0.1

        return min(score, 1.0)

    def _find_matched_signals(self, text: str) -> list[str]:
        """找出所有匹配的信号词"""
        matched = []
        all_signals = (
            self.HIGH_CONFIDENCE_SIGNALS
            + self.MEDIUM_CONFIDENCE_SIGNALS
            + self.LOW_CONFIDENCE_SIGNALS
        )
        for pattern in all_signals:
            m = re.search(pattern, text)
            if m:
                matched.append(m.group(0))
        return matched


# ─────────────────────────────────────────────────────────────────────────────
# SQLBoundaryValidator - SQL边界条件测试
# ─────────────────────────────────────────────────────────────────────────────

class SQLBoundaryValidator(BreakingValidator):
    """
    构造SQL边界条件来打破"SQL安全"的假设

    目的：验证SQL执行器是否正确处理了各种恶意/边界SQL。

    构造的边界条件：
    1. SQL注入：' OR '1'='1, '; DROP TABLE; --
    2. 超长输入：超长字符串（>10000字符）
    3. 空值处理：NULL, '', 空字符串
    4. 特殊字符：\x00, \n, \r, Unicode特殊字符
    5. 数字溢出：超出INT/BIGINT范围
    6. 嵌套查询：多层子查询

    注意：
    - 这个验证器需要能够访问SQL执行上下文
    - 实际执行需要沙箱环境
    - 设计为BreakingValidator，主动"构造"边界条件

    后续（Phase 5 TaskScheduler）会与TaskScheduler集成：
    - VERIFY类型的任务会自动触发边界验证
    """

    name = "sql_boundary"
    enabled = True

    # 边界条件SQL模板
    BOUNDARY_SQL_TEMPLATES = [
        # 注入类
        ("sql_injection_or", "SELECT * FROM users WHERE id=1 OR 1=1"),
        ("sql_injection_union", "SELECT * FROM users WHERE id=1 UNION SELECT * FROM users"),
        ("sql_injection_drop", "'; DROP TABLE users; --"),
        # 超长类
        ("long_string_10k", "SELECT * FROM users WHERE name='{}'".format("A" * 10000)),
        ("long_string_100k", "SELECT * FROM users WHERE name='{}'".format("A" * 100000)),
        # 空值类
        ("null_compare", "SELECT * FROM users WHERE name=NULL"),
        ("empty_string", "SELECT * FROM users WHERE name=''"),
        # 数字溢出
        ("int_overflow", "SELECT * FROM users WHERE id=99999999999999999999"),
        # 特殊字符
        ("special_char_newline", "SELECT * FROM users WHERE name='test\\nadmin'"),
        ("special_char_null", "SELECT * FROM users WHERE name='test\\x00admin'"),
    ]

    def __init__(self, max_test_cases: int = 5):
        """
        Args:
            max_test_cases: 最多测试的边界条件数量（防止资源耗尽）
        """
        self.max_test_cases = max_test_cases

    def break_assumption(self, context: dict) -> ValidationResult:
        """
        构造边界SQL来测试系统韧性

        这个方法分析context中的goal/tool_results，
        判断是否涉及SQL执行，如果是则构造边界测试。
        """
        # 检查是否涉及SQL
        tools_to_execute = context.get("tools_to_execute", [])
        tool_results = context.get("tool_results", [])
        goal = context.get("goal", "")

        is_sql_context = self._is_sql_context(goal, tools_to_execute)
        if not is_sql_context:
            return ValidationResult(
                broken=False,
                validator_name=self.name,
                reason="Not a SQL context, skipping boundary test",
            )

        # 检查是否有安全假设可以被打破
        # 例如：假设LLM输出的SQL都是安全的
        llm_response = context.get("llm_response", "")
        sql_claims = self._extract_sql_claims(llm_response)

        if not sql_claims:
            return ValidationResult(
                broken=False,
                validator_name=self.name,
                reason="No SQL claims to test",
            )

        # 对每条SQL构造边界测试
        for sql in sql_claims[:self.max_test_cases]:
            break_result = self._test_sql_boundaries(sql)
            if break_result.broken:
                return break_result

        return ValidationResult(
            broken=False,
            validator_name=self.name,
            reason=f"Tested {len(sql_claims[:self.max_test_cases])} SQL claims, all passed boundary tests",
        )

    def _is_sql_context(self, goal: str, tools: list[dict]) -> bool:
        """判断是否涉及SQL执行"""
        sql_keywords = ["sql", "query", "select", "insert", "update", "delete", "数据库"]
        goal_lower = goal.lower()
        return any(kw in goal_lower for kw in sql_keywords) or any(
            t.get("name", "").lower() in ["execute_sql", "query", "pg_query"]
            for t in tools
        )

    def _extract_sql_claims(self, text: str) -> list[str]:
        """从LLM输出中提取SQL语句"""
        sql_pattern = r"(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER)\s+[^\n;]{10,}"
        matches = re.findall(sql_pattern, text, re.IGNORECASE)
        return [m.strip() for m in matches if len(m) > 10]

    def _test_sql_boundaries(self, sql: str) -> ValidationResult:
        """
        对单条SQL进行边界条件测试

        这里只是框架设计，实际执行需要集成到TaskScheduler
        """
        # 检查是否有明显的安全问题（不需要实际执行）
        dangerous_patterns = [
            (r"DROP\s+TABLE", "DROP TABLE detected"),
            (r"DELETE\s+FROM\s+\w+\s*;?\s*$", "DELETE without WHERE"),
            (r"TRUNCATE", "TRUNCATE detected"),
            (r"'\s*OR\s+'1'\s*=\s*'1", "Classic SQL injection pattern"),
        ]

        for pattern, reason in dangerous_patterns:
            if re.search(pattern, sql, re.IGNORECASE):
                return ValidationResult(
                    broken=True,
                    validator_name=self.name,
                    reason=reason,
                    evidence=sql[:100],
                    suggestion="请确认此SQL是否经过安全验证",
                    severity="critical",
                )

        return ValidationResult(broken=False, validator_name=self.name)


# ─────────────────────────────────────────────────────────────────────────────
# TokenOverBudgetValidator - Token预算检查
# ─────────────────────────────────────────────────────────────────────────────

class TokenOverBudgetValidator(Validator):
    """
    检查Token是否超预算

    目的：在after_iteration中检测token_count是否达到token_budget，
    触发记忆整合（Phase 2）或强制停止。

    设计为Validator：被动检查而非主动构造。
    """

    name = "token_over_budget"
    enabled = True

    # 不同严重程度的阈值（相对于token_budget的比例）
    WARNING_THRESHOLD = 0.8  # 80% 警告
    CRITICAL_THRESHOLD = 0.95  # 95% 强制整合

    def validate(self, context: dict) -> ValidationResult:
        token_count = context.get("token_count", 0)
        token_budget = context.get("token_budget", 100000)
        iteration = context.get("iteration", 1)
        max_iterations = context.get("max_iterations", 10)

        if token_budget <= 0:
            return ValidationResult(broken=False, validator_name=self.name)

        ratio = token_count / token_budget

        if ratio >= self.CRITICAL_THRESHOLD:
            return ValidationResult(
                broken=True,
                validator_name=self.name,
                reason=f"Token预算严重超限（{ratio:.0%}），必须触发记忆整合",
                evidence=f"token_count={token_count}, budget={token_budget}",
                suggestion="Phase 2: 触发Consolidator进行记忆整合",
                severity="critical",
            )

        if ratio >= self.WARNING_THRESHOLD:
            return ValidationResult(
                broken=True,
                validator_name=self.name,
                reason=f"Token预算接近上限（{ratio:.0%}），建议触发记忆整合",
                evidence=f"token_count={token_count}, budget={token_budget}",
                suggestion="Phase 2: 考虑触发Consolidator",
                severity="warning",
            )

        # 检查迭代效率
        expected_iterations = min(max_iterations, 5)
        if iteration > expected_iterations and ratio < self.WARNING_THRESHOLD:
            return ValidationResult(
                broken=True,
                validator_name=self.name,
                reason=f"迭代效率低（迭代{iteration}次但token仅消耗{ratio:.0%}）",
                evidence=f"iteration={iteration}, token_ratio={ratio:.0%}",
                suggestion="考虑优化迭代策略",
                severity="info",
            )

        return ValidationResult(broken=False, validator_name=self.name)
